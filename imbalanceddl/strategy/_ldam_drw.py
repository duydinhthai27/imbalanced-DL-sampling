import numpy as np
import torch
from .trainer import Trainer

from imbalanceddl.utils.utils import AverageMeter
from imbalanceddl.utils.metrics import accuracy
from imbalanceddl.loss import LDAMLoss


class LDAMDRWTrainer(Trainer):
    """LDAM-DRW Trainer

    Strategy: LDAM Loss with DRW training schedule
    Reference
    ----------
    Learning Imbalanced Datasets with Label-Distribution-Aware Margin Loss
    https://arxiv.org/pdf/1906.07413.pdf
    https://github.com/kaidic/LDAM-DRW
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_criterion(self):
        if self.strategy == 'LDAM_DRW':
            if self.cfg.epochs == 300:
                idx = self.epoch // 250
            else:
                idx = self.epoch // 160
            betas = [0, 0.9999]
            effective_num = 1.0 - np.power(betas[idx], self.cls_num_list)
            per_cls_weights = (1.0 - betas[idx]) / np.array(effective_num)
            per_cls_weights = per_cls_weights / np.sum(per_cls_weights) * len(
                self.cls_num_list)
            per_cls_weights = torch.FloatTensor(per_cls_weights).cuda(
                self.cfg.gpu)
            print("=> LDAM Loss with Per Class Weight = {}".format(
                per_cls_weights))
            self.criterion = LDAMLoss(cls_num_list=self.cfg.cls_num_list,
                                      max_m=0.5,
                                      s=30,
                                      weight=per_cls_weights).cuda(
                                          self.cfg.gpu)
        else:
            raise ValueError("[Warning] Strategy is not supported !")

    def train_one_epoch(self):
        # Record
        losses = AverageMeter('Loss', ':.4e')
        top1 = AverageMeter('Acc@1', ':6.2f')
        top5 = AverageMeter('Acc@5', ':6.2f')

        # for confusion matrix
        all_preds = list()
        all_targets = list()

        # switch to train mode
        self.model.train()

        for i, (_input, target) in enumerate(self.train_loader):

            if self.cfg.gpu is not None:
                _input = _input.cuda(self.cfg.gpu, non_blocking=True)
                target = target.cuda(self.cfg.gpu, non_blocking=True)

            # print("=> LDAM DRW training")
            out, _ = self.model(_input)
            loss = self.criterion(out, target).mean()
            acc1, acc5 = accuracy(out, target, topk=(1, 5))
            _, pred = torch.max(out, 1)
            all_preds.extend(pred.cpu().numpy())
            all_targets.extend(target.cpu().numpy())

            # measure accuracy and record loss
            losses.update(loss.item(), _input.size(0))
            top1.update(acc1[0], _input.size(0))
            top5.update(acc5[0], _input.size(0))

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

            if i % self.cfg.print_freq == 0:
                output = ('Epoch: [{0}][{1}/{2}], lr: {lr:.5f}\t'
                          'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                          'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                          'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                              self.epoch,
                              i,
                              len(self.train_loader),
                              loss=losses,
                              top1=top1,
                              top5=top5,
                              lr=self.optimizer.param_groups[-1]['lr'] * 0.1))
                print(output)
                self.log_training.write(output + '\n')
                self.log_training.flush()

        self.compute_metrics_and_record(all_preds,
                                        all_targets,
                                        losses,
                                        top1,
                                        top5,
                                        flag='Training')
