import pickle
import time
import builtins
import sys
import torch
import numpy as np
import os
import shutil
from copy import deepcopy
import json

class EMA():
    '''
    Exponential moving average
    '''
    def __init__(self, beta = 0.98):

        self.beta = beta
        self.itr_idx = 0
        self.average_value = 0

    def update(self, value):
        self.itr_idx += 1
        self.average_value = self.beta * self.average_value + (1-self.beta)*value
        smoothed_average = self.average_value / (1 - self.beta**(self.itr_idx))
        return smoothed_average

class dotdict(dict):
    '''
    dot.notation access to dictionary attributes
    '''
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")

def list2range(v):
    r = []
    for num in v:
        if not ':' in num:
            r.append(int(num))
        else:
            k = [int(x) for x in num.split(':')]
            if len(k)==2:
                r.extend(list(range(k[0],k[1]+1)))
            else:
                r.extend(list(range(k[0],k[1]+1,k[2])))
    return r

def get_chunks(seq_tokens, N_tokens_chunk, N_tokens_overlap, tokenizer_cls_token_id=None,
                  tokenizer_eos_token_id=None, tokenizer_pad_token_id=None, padding=False,):

    '''
    Chunk tokenized sequence into chunks of length N_tokens_chunk,
    overlapping by N_tokens_overlap tokens
    The input sequence shouldn't contain any special tokens (e.g. cls,sep,eos)
    The last chunk is padded on the left using the last tokens of the previous chunk
    '''
    is_cls_token = tokenizer_cls_token_id is not None
    is_eos_token = tokenizer_eos_token_id is not None

    chunk_len = N_tokens_chunk-is_cls_token-is_eos_token #actual sequence length

    N_tokens_overlap = min(N_tokens_overlap,chunk_len-1)

    chunks = [seq_tokens[start:start+chunk_len] for start in range(0,max(len(seq_tokens)-N_tokens_overlap,1),chunk_len-N_tokens_overlap)]

    #print(chunks)
    
    #if len(chunks)>1 and len(chunks[-1])<=N_tokens_overlap:
    #    del chunks[-1]

    #pad the last chunk on the left with the tokens from the previous chunk
    if len(chunks)>1:
        left_shift = min(chunk_len-len(chunks[-1]), len(chunks[-2])-N_tokens_overlap)
        if left_shift>0:
            pad_seq = chunks[-2][-left_shift-N_tokens_overlap:len(chunks[-2])-N_tokens_overlap]
            chunks[-1] = pad_seq + chunks[-1]
    else:
        left_shift = 0

    assert [x for y in chunks[:-1] for x in y[:len(y)-N_tokens_overlap]]+[x for x in  chunks[-1][left_shift:]] 

    #add cls and eos tokens to each chunk
    if is_cls_token:
        chunks = [[tokenizer_cls_token_id, *chunk] for chunk in chunks]
    
    if is_eos_token:
        chunks = [[*chunk, tokenizer_eos_token_id] for chunk in chunks]

    #add padding on the right
    if padding:
        chunks = [[*chunk, *[tokenizer_pad_token_id]*(N_tokens_chunk-len(chunk))] for chunk in chunks]

    return chunks, left_shift

def print(*args, **kwargs):
    '''
    Redefine print function for logging
    '''
    now = time.strftime("[%Y/%m/%d-%H:%M:%S]-", time.localtime()) #current date and time at the beggining of each printed line
    builtins.print(now, *args, **kwargs)
    sys.stdout.flush()

def save_model_weights(model, optimizer, scheduler, output_dir, epoch, save_at):
    '''
    Save model and optimizer weights
    '''

    checkpoint_name = f'epoch_{epoch}'

    config_save_base = os.path.join(output_dir, checkpoint_name)

    print(f'SAVING MODEL, CHECKPOINT DIR: {config_save_base}\n')

    model.save_pretrained(config_save_base)

    #torch.save(model.state_dict(), config_save_base+'_model') #save model weights

    torch.save(optimizer.state_dict(), config_save_base+'/optimizer.pt') #save optimizer weights

    torch.save(scheduler.state_dict(), config_save_base+'/scheduler.pt') #save optimizer weights

    for checkpoint in os.listdir(output_dir):
        checkpoint_epoch = int(checkpoint.split('_')[-1])
        if checkpoint.startswith('epoch_') and checkpoint!=checkpoint_name and checkpoint_epoch not in save_at:
            shutil.rmtree(os.path.join(output_dir, checkpoint))

def mask_tokens(inputs, tokenizer, mlm_probability):
    """ Prepare masked tokens inputs/labels for masked language modeling: 80% MASK, 10% random, 10% original. """

    mask_list = [-2, -1, 1, 2, 3] #6-mer

    if tokenizer.mask_token is None:
        raise ValueError(
            "This tokenizer does not have a mask token which is necessary for masked language modeling. Remove the --mlm flag if you want to use this tokenizer."
        )

    labels = inputs.clone()
    # We sample a few tokens in each sequence for masked-LM training (with probability args.mlm_probability defaults to 0.15 in Bert/RoBERTa)
    probability_matrix = torch.full(labels.shape, mlm_probability)
    special_tokens_mask = [
        tokenizer.get_special_tokens_mask(val, already_has_special_tokens=True) for val in labels.tolist()
    ]
    probability_matrix.masked_fill_(torch.tensor(special_tokens_mask, dtype=torch.bool), value=0.0)
    if tokenizer._pad_token is not None:
        padding_mask = labels.eq(tokenizer.pad_token_id)
        probability_matrix.masked_fill_(padding_mask, value=0.0)

    masked_indices = torch.bernoulli(probability_matrix).bool()

    # change masked indices
    masks = deepcopy(masked_indices)
    for i, masked_index in enumerate(masks):
        end = torch.where(probability_matrix[i]!=0)[0].tolist()[-1]
        mask_centers = set(torch.where(masked_index==1)[0].tolist())
        new_centers = deepcopy(mask_centers)
        for center in mask_centers:
            for mask_number in mask_list:
                current_index = center + mask_number
                if current_index <= end and current_index >= 1:
                    new_centers.add(current_index)
        new_centers = list(new_centers)
        masked_indices[i][new_centers] = True

    labels[~masked_indices] = -100  # We only compute loss on masked tokens

    # 80% of the time, we replace masked input tokens with tokenizer.mask_token ([MASK])
    indices_replaced = torch.bernoulli(torch.full(labels.shape, 0.8)).bool() & masked_indices
    inputs[indices_replaced] = tokenizer.convert_tokens_to_ids(tokenizer.mask_token)

    # 10% of the time, we replace masked input tokens with random word
    indices_random = torch.bernoulli(torch.full(labels.shape, 0.5)).bool() & masked_indices & ~indices_replaced
    random_words = torch.randint(len(tokenizer), labels.shape, dtype=torch.long)
    inputs[indices_random] = random_words[indices_random]

    # The rest of the time (10% of the time) we keep the masked input tokens unchanged
    return inputs, labels

def worker_init_fn(worker_id):
     worker_info = torch.utils.data.get_worker_info()
     dataset = worker_info.dataset  # the dataset copy in this worker process
     overall_start = dataset.start
     overall_end = dataset.end
     # configure the dataset to only process the split workload
     per_worker = int(np.ceil((overall_end - overall_start) / float(worker_info.num_workers)))
     worker_id = worker_info.id
     dataset.start = overall_start + worker_id * per_worker
     dataset.end = min(dataset.start + per_worker, overall_end)
