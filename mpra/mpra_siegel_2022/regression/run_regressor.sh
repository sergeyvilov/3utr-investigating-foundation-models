#!/bin/bash

#################################################################
#
#Run SVR on Siegel MPRA data
#
#
#sbatch --array=0-88 run_regressor.sh
#################################################################

#SBATCH -J siegel_regr
#SBATCH -c 10
#SBATCH --mem=64G
#SBATCH -p cpu_p
#SBATCH --qos=cpu_normal
#SBATCH --time=2-00:00:00
#SBATCH --nice=10000
#SBATCH -o /lustre/groups/epigenereg01/workspace/projects/vale/mlm/slurm_logs/%x-%A_%a.o
#SBATCH -e /lustre/groups/epigenereg01/workspace/projects/vale/mlm/slurm_logs/%x-%A_%a.e

data_dir='/lustre/groups/epigenereg01/workspace/projects/vale/mlm/mpra/siegel_2022/'

source ~/.bashrc; conda activate ntrans

export LD_LIBRARY_PATH=~/miniconda3/lib

c=0

for onlyref in 0;do

    for regressor in Ridge SVR MLP; do

    output_dir="${data_dir}/predictions/onlyref_$onlyref/${regressor}/"

    mkdir -p $output_dir

        for response in stability steady_state; do

            for cell_type in Jurkat Beas2B; do

                mpra_tsv="${data_dir}/${cell_type}.tsv"

                for model in dnabert dnabert2 ntrans-v2-250m ntrans-v2-500m dnabert-3utr dnabert2-3utr ntrans-v2-250m-3utr stspace stspace-spaw 5mers; do

                    if [ ${SLURM_ARRAY_TASK_ID} -eq $c ]; then

                        if [[ ! $model =~ "mers" ]] && [[ $model != "effective_length" ]]; then
                            embeddings="--embeddings $data_dir/embeddings/$model/predictions.pickle"
                        fi

                        if [[ $regressor = "MLP" ]]; then
                            n_hpp_trials=150
                        else
                            n_hpp_trials=300
                        fi

                        output_name=$output_dir/${cell_type}-${response}-${model}.tsv

                        #if ! [ -f "${output_name}" ]; then

                            echo $output_name

                            params="--mpra_tsv $mpra_tsv --model $model $embeddings \
                            --response $response --onlyref $onlyref --regressor $regressor \
                            --n_hpp_trials ${n_hpp_trials} --cv_splits_hpp 5  \
                            --output_name $output_name --seed 1  --n_jobs 10 "

                            python -u run_regressor.py ${params} > ${output_dir}/${cell_type}-${response}-${model}.log  2>${output_dir}/${cell_type}-${response}-${model}.err

                        #fi
                    fi

                    c=$((c+1))
                done
            done
        done
    done
done
