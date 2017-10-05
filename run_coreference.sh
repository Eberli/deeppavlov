#!/usr/bin/env bash

#parlai.agents.repeat_label.repeat_label
export CUDA_VISIBLE_DEVICES=1; python3 ./utils/train_model.py -t deeppavlov.tasks.coreference.agents:BaseTeacher \
                         -m deeppavlov.agents.coreference.agents:CoreferenceAgent \
                         -mf ./build/coreference/ \
                         --model-file 'train_model' \
		         --language russian \
			 --name fasttext \
			 --pretrained_model True \
                         -dt train:ordered \
                         --batchsize 1 \
                         --display-examples False \
                         --max-train-time -1 \
                         --validation-every-n-epochs 30 \
                         --log-every-n-epochs 10 \
                         --log-every-n-secs -1 \
                         --chosen-metric conll-F-1 \

