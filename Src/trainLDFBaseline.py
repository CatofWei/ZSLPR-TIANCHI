# -*- coding: utf-8 -*-
# Tianchi competition：zero-shot learning competition
# Team: AILAB-ZJU
# Code function：run training of LDF baseline
# Author: Yinda XU

# import installed packages
import os
import shutil
import pickle
import numpy as np
import pandas as pd

import sklearn
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

import torch
from torch import Tensor
from torch import LongTensor
from torch import nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

# import in-house packages
from dataset import datasetZSL, datasetZSL_wtDataAug
import models
from models import LDF_baseline
from models.loss import loss_LDF_CE_TriHard

# import config
import config
from config import *

import utils
from utils.wheels import *
from utils.trainer import trainer_epoch
from utils.DataAug import data_aug_ZSL
# Make experiment result folder
TimeStamp, path_folderExp, path_folderExpBestModel = utils.backup.createBackUp()

from prepareData import *

# Make dataset
dataset_trn = datasetZSL(path_folderTrainImage, path_txtImageLabel, index_split=index_SeenTrn,    label_enc=label_enc, data_aug=data_aug_ZSL,)
dataset_val = datasetZSL(path_folderTrainImage, path_txtImageLabel, index_split=index_SeenVal, label_enc=label_enc)
dataset_tst = datasetZSL(path_folderTrainImage, path_txtImageLabel, index_split=index_UnseenTst, label_enc=label_enc)
dataset_prd = datasetZSL(path_folderTestImage, path_txtImage, index_split=index_UnseenPrd, label_enc=label_enc, DummyTarget=True)
dataset_prd_DataAug = datasetZSL_wtDataAug(datasetZSL(
        path_folderTestImage, path_txtImage, index_split=index_UnseenPrd,
        label_enc=label_enc, DummyTarget=True, data_aug=data_aug_ZSL,
), num_DataAug = 16)

# Make dataloader
dataloader_trn = torch.utils.data.DataLoader(
    dataset=dataset_trn, batch_size=params_batch_size, shuffle=True,
    num_workers = params_num_workers,pin_memory=True,
)
dataloader_trn_TriHard = torch.utils.data.DataLoader(
    dataset=dataset_trn, batch_size=params_batch_size_TriHard, shuffle=True,
    num_workers = params_num_workers,pin_memory=True,
)
dataloader_val = torch.utils.data.DataLoader(
    dataset=dataset_val, batch_size=params_batch_size, shuffle=False,
    num_workers = params_num_workers,pin_memory=True,
)
dataloader_tst = torch.utils.data.DataLoader(
    dataset=dataset_tst, batch_size=params_batch_size, shuffle=False,
    num_workers = params_num_workers,pin_memory=True,
)
dataloader_prd = torch.utils.data.DataLoader(
    dataset=dataset_prd, batch_size=params_batch_size, shuffle=False,
    num_workers = params_num_workers,pin_memory=True,
)
dataloader_prd_DataAug = torch.utils.data.DataLoader(
    dataset=dataset_prd_DataAug, batch_size=dataset_prd_DataAug.num_DataAug, shuffle=False,
    num_workers = params_num_workers,pin_memory=True,
)


torch.cuda.set_device(params_cuda_device)
# Model & Loss
model = LDF_baseline(
    arr_ClassEmbed=arr_ClassNameVec, dimVisFeat=params_dimVisFeat,
    NormalizedLogit=True, RetLogits=params_useTriHardLoss,
).cuda()
# ClassWeight = 1/(sr_ImageLabel.value_counts()[sr_LabelEnc[sr_ImageLabel.unique()].sort_values().index].values)
# criterion = nn.CrossEntropyLoss(weight=Tensor(ClassWeight)).cuda()
if params_useTriHardLoss:
    criterion = loss_LDF_CE_TriHard(
        margin=params_TriHardMargin, coeff_TriHard=params_coeff_TriHardLoss,
    ).cuda()
    print('Use TriHard loss.')
else:
    criterion = nn.CrossEntropyLoss().cuda()
    print('Use CrossEntropy loss.')

lrs_epoch = []
losses_epoch = []
accus_epoch = []

optimizer = torch.optim.SGD(
    filter(lambda p: p.requires_grad, model.parameters()),
    lr=params_lr, weight_decay=params_weight_decay,
)
# lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(
#     optimizer, gamma=0.975,
# )
lr_scheduler = torch.optim.lr_scheduler.LambdaLR(
    optimizer, params_func_lr, # lambda n:(1-n/params_NEpochs)**0.9
)
# optimizer, lr_schduler = config.optimizer.get_Optim_LRSchdl(model)
# config.optimizer.save_LRSchdl(os.path.join(path_folderExp, r'lr_scheduling.png'))

NEpochs = params_NEpochs

path_pklLog = os.path.join(path_folderExp, r'ExperimentLog.pkl')
path_fileModelStatePrev = ''

print('******************* Training Start *******************')
with print_elapsed_time(prompt='Training part'):
    accu_best = 0
    if False:
        loss_avg_val, accu_avg_val = trainer_epoch(
            model, dataloader_val, criterion,
        )
        print('Init cond:', loss_avg_val, accu_avg_val)
    for ith_epoch in range(NEpochs):
        time_start = time.time()
        loss_avg_trn, loss_avg_val, loss_avg_tst, accu_avg_val, accu_avg_tst = \
            0,0,0,0,0
        if params_useLRScheduler:
            lr_scheduler.step()
        loss_avg_trn, accu_avg_trn, loss_avg_val, accu_avg_val = 0,0,0,0
        loss_avg_tst, accu_avg_tst, loss_avg_prd, accu_avg_prd = 0,0,0,0
        arr_outputs_prd = None

# train model for one epoch
        if True:
            if params_useTriHardLoss and ith_epoch > params_EpochTriHardBatch:
                dataloader_trn_ = dataloader_trn_TriHard
            else:
                dataloader_trn_ = dataloader_trn
            loss_avg_trn, accu_avg_trn = trainer_epoch(
                model, dataloader_trn_, criterion,
                training=True, optimizer=optimizer,
                idxCat=LongTensor(idxCatAnnotd).cuda(),
            )
# # validate model with validation set
        if True:
            loss_avg_val, accu_avg_val = trainer_epoch(
                model, dataloader_val, criterion,
            )
        SaveBest = accu_avg_val>accu_best
# # Test
        if params_LocalTest:
            loss_avg_tst, accu_avg_tst = trainer_epoch(
                model, dataloader_tst, criterion,
                idxCat=LongTensor(idxCatUnseen).cuda(),
            )
# Predict
        if SaveBest and ith_epoch>int(NEpochs*0.8):
            if params_useTestAug:
                dataloader_prd_=dataloader_prd_DataAug
            else:
                dataloader_prd_=dataloader_prd
            arr_outputs_prd = trainer_epoch(
                model,
                dataloader_prd_,
                criterion,
                predict=True,
                predict_DataAug=params_useTestAug,
                idxCat=LongTensor(idxCatUnannotd).cuda(),
            )

        time_elapsed = time.time()-time_start

        EpochResult = r'TRN_lss_{:.3g}_accu_{:.3g}_VAL_lss_{:.3g}_accu_{:.3g}_TST_lss_{:.3g}_accu_{:.3g}'.format(
            loss_avg_trn,accu_avg_trn, loss_avg_val, accu_avg_val, loss_avg_tst, accu_avg_tst,)

        # print epoch log
        lr_epoch = optimizer.param_groups[0]['lr']
        if ith_epoch % 1 == 0:
            print('Epoch {}/{}, {:.1f}[s] elapsed, {:s}, lr: {:.3g}'.format(
                ith_epoch+1, NEpochs, time_elapsed, EpochResult, lr_epoch,))
            print('Log saved at:', path_folderExp)
        lrs_epoch.append(lr_epoch)
        losses_epoch.append((loss_avg_trn, loss_avg_val, loss_avg_tst))
        accus_epoch.append((accu_avg_trn, accu_avg_val, accu_avg_tst))
        # Save log
        dict_Log = {
            'lrs_epoch':lrs_epoch,
            'losses_epoch':losses_epoch,
            'accus_epoch':accus_epoch,
        }
        with open(path_pklLog, 'wb') as f:
            pickle.dump(dict_Log, f)

        # Save best
        if params_SaveBest and SaveBest:
            model_result = r'{:s}_Ep_{:d}_{:s}'.format(
                type(model).__name__, ith_epoch+1,  EpochResult
            )
            if path_fileModelStatePrev:
                os.remove(path_fileModelStatePrev)
            path_fileModelState = os.path.join(
                path_folderExpBestModel, r'{:s}.ptmdl'.format(model_result, ),
            )
            torch.save(model.state_dict(), path_fileModelState)
            path_fileModelStatePrev = path_fileModelState
            accu_best = accu_avg_val
            # Save predict result
            if not isinstance(arr_outputs_prd, type(None)):
                sr_outputs_prd = pd.Series(sr_LabelEncInv[arr_outputs_prd.squeeze()].values, index=sr_Image[index_UnseenPrd].index)
                path_txtSub = os.path.join(
                    path_folderExp, r'submit_{:s}.txt'.format(model_result)
                )
                sr_outputs_prd.to_csv(path_txtSub, sep='\t')
print('BestModelSavedAt:')
print(path_fileModelState)
