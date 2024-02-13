#!/bin/bash

#################################################################
#
#Run logistic regression on embeddings
#
#
#sbatch --array=0-72 run_classify.sh
#################################################################

#SBATCH -J cls_variants
#SBATCH -c 10
#SBATCH --mem=64G
#SBATCH -p cpu_p
#SBATCH --qos=cpu_normal
#SBATCH --time=2-00:00:00
#SBATCH --nice=10000
#SBATCH -o /lustre/groups/epigenereg01/workspace/projects/vale/mlm/slurm_logs/%x-%j.o
#SBATCH -e /lustre/groups/epigenereg01/workspace/projects/vale/mlm/slurm_logs/%x-%j.e

data_dir='/lustre/groups/epigenereg01/workspace/projects/vale/mlm/variants/'

data_tsv="${data_dir}/selected/variants_snp.tsv"

source ~/.bashrc; conda activate ntrans

export LD_LIBRARY_PATH=~/miniconda3/lib

c=0

for merge_embeddings in 1;do

  for classifier in MLP; do

      output_dir="${data_dir}/predictions/merge_embeddings_${merge_embeddings}/$classifier/"

      mkdir -p $output_dir

      for model in dnabert dnabert2 ntrans-v2-250m dnabert-3utr dnabert2-3utr ntrans-v2-250m-3utr  stspace stspace-spaw ntrans-v2-500m; do
          
          for subset in clinvar gnomAD eQTL-susie eQTL-GRASP; do

                  if [ ${SLURM_ARRAY_TASK_ID} -eq $c ]; then

                      output_name=$output_dir/$subset-$model.tsv

                      #if ! [ -f "${output_name}" ]; then

                          embeddings="$data_dir/embeddings/$model/predictions.pickle"

                          echo $output_name

                          params="--data_tsv $data_tsv --embeddings ${embeddings}  --classifier $classifier \
                          --subset $subset --output_name $output_name --merge_embeddings ${merge_embeddings} \
                          --seed 1  --n_jobs 10 "

                          python -u run_classify.py ${params} > ${output_dir}/$subset-$model.log  2>${output_dir}/$subset-$model.err

                      #fi
                  fi

                  c=$((c+1))
          done
      done
  done
done
