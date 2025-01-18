import torch
import torch.nn as nn
from .trainer import Trainer
import wandb
from imbalanceddl.utils.utils import AverageMeter
from imbalanceddl.utils.metrics import accuracy


class ERMTrainer(Trainer):
    """ERM Trainer

    Strategy: Empirical Risk Minimization
    basically, training with each class sharing the same weights.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_criterion(self):
        if self.strategy == 'ERM':
            per_cls_weights = None
            print("=> CE Loss with Per Class Weight = {}".format(
                per_cls_weights))
            self.criterion = nn.CrossEntropyLoss(weight=per_cls_weights,
                                                 reduction='none').cuda(
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

            # print("=> ERM training")
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
                wandb.log({
                    "epoch": self.epoch,
                    "epoch_train_loss": losses.avg,
                    "epoch_train_acc@1": top1.avg,
                    "epoch_train_acc@5": top5.avg,
                    "lr": self.optimizer.param_groups[-1]['lr'] * 0.1
                    })

        self.compute_metrics_and_record(all_preds,
                                        all_targets,
                                        losses,
                                        top1,
                                        top5,
                                        flag='Training')
