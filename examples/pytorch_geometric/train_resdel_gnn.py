import numpy as np
import os
import math
from tqdm import tqdm
import argparse
import datetime
import time
import logging

import dotenv as de
de.load_dotenv()

import sys
sys.path.append('../..')

import torch
import torch.nn as nn
from torch.utils import data
from torch_geometric.data import Data, Batch, DataLoader
from torch_geometric.nn import GCNConv, global_add_pool, DataParallel
from torch.nn import Sequential, Linear, ReLU
import torch.nn.functional as F


# import atom3d.util.datatypes as dt
import atom3d.util.shard as sh
import resdel_dataloader as dl



class GCN(torch.nn.Module):
    def __init__(self, num_features, hidden_dim):
        super(GCN, self).__init__()
        self.conv1 = GCNConv(num_features, hidden_dim)
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.conv2 = GCNConv(hidden_dim, hidden_dim*2)
        self.bn2 = nn.BatchNorm1d(hidden_dim*2)
        self.conv3 = GCNConv(hidden_dim*2, hidden_dim*4)
        self.bn3 = nn.BatchNorm1d(hidden_dim*4)
        self.conv4 = GCNConv(hidden_dim*4, hidden_dim*4)
        self.bn4 = nn.BatchNorm1d(hidden_dim*4)
        self.conv5 = GCNConv(hidden_dim*4, hidden_dim*2)
        self.bn5 = nn.BatchNorm1d(hidden_dim*2)
        self.fc1 = Linear(hidden_dim*2, hidden_dim*2)
        self.fc2 = Linear(hidden_dim*2, 20)


    def forward(self, x, edge_index, edge_weight, batch):
        x = self.conv1(x, edge_index, edge_weight)
        x = F.relu(x)
        x = self.bn1(x)
        x = self.conv2(x, edge_index, edge_weight)
        x = F.relu(x)
        x = self.bn2(x)
        x = self.conv3(x, edge_index, edge_weight)
        x = F.relu(x)
        x = self.bn3(x)
        x = self.conv4(x, edge_index, edge_weight)
        x = self.bn4(x)
        x = F.relu(x)
        x = self.conv5(x, edge_index, edge_weight)
        x = self.bn5(x)
        x = global_add_pool(x, batch)
        x = F.relu(x)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, p=0.25, training=self.training)
        return self.fc2(x)


def get_acc(logits, label, cm=None):
    pred = torch.argmax(logits, 1)
    acc = float((pred == label).sum(-1)) / label.size()[0]
    return acc

# from pytorch ...
def get_top_k_acc(output, target, k=3):
    """Computes the accuracy over the k top predictions for the specified values of k"""
    with torch.no_grad():
        batch_size = target.size(0)

        _, pred = output.topk(k, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
        #res.append(correct_k.mul_(100.0 / batch_size))
        return correct_k.mul_(1.0 / batch_size).item()


@torch.no_grad()
def test(model, loader, criterion, device):
    model.eval()

    losses = []
    avg_acc = []
    avg_top_k_acc = []
    for i, graph in enumerate(loader):
        graph = graph.to(device)
        out = model(graph.x, graph.edge_index, graph.edge_attr.view(-1), graph.batch)
        loss = criterion(out, graph.y)
        acc = get_acc(out, graph.y)
        top_k_acc = get_top_k_acc(out, graph.y, k=3)
        losses.append(loss.item())
        avg_acc.append(acc)
        avg_top_k_acc.append(top_k_acc)

    return np.mean(losses), np.mean(avg_acc), np.mean(avg_top_k_acc)


def train(data_dir, device, log_dir, checkpoint, seed=None, test_mode=False):

    epochs = 5
    batch_size = 64
    in_channels = 5
    learning_rate = 1e-4
    reg = 5e-6
    
    if not os.path.exists(os.path.join(log_dir, 'params.txt')):
        with open(os.path.join(log_dir, 'log.txt'), 'w') as f:
            f.write(f'Epochs: {epochs}\n')
            f.write(f'Batch size: {batch_size}\n')
            f.write(f'Learning rate: {learning_rate}\n')

    train_set = dl.Resdel_Dataset_PTG(os.path.join(data_dir, 'train'))
    train_loader = DataLoader(train_set, batch_size=batch_size, num_workers=8, shuffle=True)
    val_set = Resdel_Dataset_PTG(os.path.join(data_dir, 'val'))
    val_loader = DataLoader(val_set, batch_size=batch_size, num_workers=8, shuffle=True)

    for graph in train_loader:
        num_features = graph.num_features
        break

    model = GCN(num_features, hidden_dim=64)
    model.to(device)
    # if torch.cuda.device_count() > 1:
    #     print('using', torch.cuda.device_count(), 'GPUs')
    #     parallel = True
    #     model = DataParallel(model)
    model.train()

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)#, weight_decay=reg)
    criterion = nn.CrossEntropyLoss()
    criterion.to(device)

    if checkpoint:
        cpt = torch.load(checkpoint, map_location=device)
        model.load_state_dict(cpt['model_state_dict'])
        optimizer.load_state_dict(cpt['optimizer_state_dict'])

    best_val_loss = 999
    best_val_idx = 0
    print_frequency = 100

    for epoch in range(1, epochs+1):
        print(f'EPOCH {epoch}\n------------')

        start = time.time()

        for it, graph in enumerate(train_loader):
            graph = graph.to(device)
            optimizer.zero_grad()
            out = model(graph.x, graph.edge_index, graph.edge_attr.view(-1), graph.batch)
            train_loss = criterion(out, graph.y)
            train_loss.backward()
            optimizer.step()


            if it % print_frequency == 0:
                elapsed = time.time() - start
                print(f'Epoch {epoch}, iter {it}, train loss {train_loss}, avg it/sec {print_frequency / elapsed}')
                start = time.time()
        print('validating...')
        curr_val_loss, val_acc, val_top_k_acc = test(model, val_loader, criterion, device)
        # logger.info('{:03d}\t{}\t{:.7f}\t{:.7f}\t{:.7f}\t{:.7f}\n'.format(epoch, it, train_loss, curr_val_loss, val_acc, val_top_k_acc))
        # print('{:03d}\t{}\t{:.7f}\t{:.7f}\t{:.7f}\t{:.7f}\n'.format(epoch, it, train_loss, curr_val_loss, val_acc, v'al_top_k_acc))
        print(f'Epoch {epoch}, iter {it}, val loss {curr_val_loss}, val acc {val_acc}, val top 3 acc {val_top_k_acc}')

        if curr_val_loss < best_val_loss:

            # save best validation score and iteration number
            best_val_loss = curr_val_loss
            best_val_idx = it
            # overwrite best model
            if parallel:
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.module.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'loss': train_loss,
                    }, os.path.join(log_dir, f'checkpoint_epoch{epoch}_it{it}.pt'))
            else:
                torch.save({
                    'epoch': epoch,
                    'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict(),
                    'loss': train_loss,
                    }, os.path.join(log_dir, f'checkpoint_epoch{epoch}_it{it}.pt'))

            model.train()

    if test_mode:
        print('testing...')
        model = cnn_3d_new(nic=in_channels).to(device)
        model.eval()
        test_set = dl.Resdel_Dataset_PTG(os.path.join(data_dir, 'test_unbalanced'))
        test_loader = DataLoader(test_set, batch_size=batch_size, num_workers=8, shuffle=True)
        cpt = torch.load(os.path.join(log_dir, f'best_weights.pt'))
        # cpt = torch.load(checkpoint, map_location=device)
        model.load_state_dict(cpt['model_state_dict'])
        test_loss, test_acc, test_top_k_acc = test(model, test_loader, criterion, device)
        print('Test loss: {:7f}, Test Accuracy {:.4f}, Top 3 Accuracy {:4f}, F1 Score {:4f}'.format(test_loss, test_acc, test_top_k_acc, test_f1))
        return test_loss, test_acc, test_top_k_acc

    return best_val_loss


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', type=str, default='train')
    parser.add_argument('--log_dir', type=str, default=None)
    parser.add_argument('--checkpoint', type=str, default=None)
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    log_dir = args.log_dir

    base_dir = '../../data/residue_deletion'
    data_dir = SC_DIR+'atom3d/graph_pt'

    if args.mode == 'train':
        if log_dir is None:
            now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
            log_dir = os.path.join(base_dir, 'logs_cnn', now)
        else:
            log_dir = os.path.join(base_dir, 'logs_cnn', log_dir)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        train(data_dir, device, log_dir, args.checkpoint)
    elif args.mode == 'test':
        test_loss_list = []
        acc_list = []
        f1_list = []
        for seed in np.random.randint(0, 100, size=3):
            print('seed:', seed)
            log_dir = os.path.join(base_dir, 'logs_cnn', f'test_{seed}')
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            np.random.seed(seed)
            torch.manual_seed(seed)
            test_loss, test_acc, test_top_k_acc, test_f1 = train(data_dir, device, log_dir, args.checkpoint, seed=seed, test_mode=True)
            test_loss_list.append(test_loss)
            acc_list.append(test_acc)
            f1_list.append(test_f1)
        print(f'Avg test_loss: {np.mean(test_loss_list)}, St.Dev test_loss {np.std(test_loss_list)}, \
            Avg accuracy {np.mean(acc_list)}, St.Dev accuracy {np.std(acc_list)},\
            Avg F1 {np.mean(f1_list)}, St.Dev F1 {np.std(f1_list)}')