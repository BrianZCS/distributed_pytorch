import os
import torch
import json
import copy
import numpy as np
from torchvision import datasets, transforms
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import logging
import random
import model as mdl
import argparse
from datetime import datetime, timedelta
from torch.nn.parallel import DistributedDataParallel

device = "cpu"
torch.set_num_threads(4)



batch_size = 256 # batch for one node
def train_model(model, train_loader, optimizer, criterion, epoch, args):
    """
    model (torch.nn.module): The model created to train
    train_loader (pytorch data loader): Training data loader
    optimizer (optimizer.*): A instance of some sort of optimizer, usually SGD
    criterion (nn.CrossEntropyLoss) : Loss function used to train the network
    epoch (int): Current epoch number
    """
    running_loss = 0.0
    time_per_iteration = timedelta(seconds=0)
    # remember to exit the train loop at end of the epoch
    for batch_idx, (data, target) in enumerate(train_loader):
        begin_time = datetime.now()
        # Your code goes here!
        optimizer.zero_grad()
        outputs = model(data)
        loss = criterion(outputs, target)
        loss.backward()

        optimizer.step()
        running_loss += loss.item()
        if batch_idx != 0:
            time_per_iteration += (datetime.now() - begin_time)
        if batch_idx % 20 == 19:
            print(f'Epoch: {epoch + 1}, Iteration: {batch_idx-18}-{batch_idx+1}, Average Loss: {running_loss / 20:.3f}')
            running_loss = 0.0
        if batch_idx % 40 == 39:
            if batch_idx == 39:
                print(f'Avg Time for iteration {batch_idx-37}-{batch_idx+1}: {time_per_iteration.total_seconds() /39} seconds.')
            else:
                print(f'Avg Time for iteration {batch_idx-38}-{batch_idx+1}: {time_per_iteration.total_seconds() /40} seconds.')
            time_per_iteration = timedelta(seconds=0)

    return None

def test_model(model, test_loader, criterion):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for batch_idx, (data, target) in enumerate(test_loader):
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += criterion(output, target)
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader)
    print('Test set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, len(test_loader.dataset),
            100. * correct / len(test_loader.dataset)))


def main():
    torch.manual_seed(1)
    parser = argparse.ArgumentParser(
                    prog='Input arguments',
                    description='gather ip, nunber of workers, rank')
    parser.add_argument('--master-ip',required=True)
    parser.add_argument('--num-nodes',required=True, type=int)
    parser.add_argument('--rank', required=True, type=int)
    args = parser.parse_args()
    master_ip = args.master_ip
    num_nodes = args.num_nodes
    rank = args.rank
    torch.distributed.init_process_group(backend='gloo', init_method='tcp://' + master_ip + ':6585', timeout=None, world_size=num_nodes, rank=rank)

    print("test")
    normalize = transforms.Normalize(mean=[x/255.0 for x in [125.3, 123.0, 113.9]],
                                std=[x/255.0 for x in [63.0, 62.1, 66.7]])
    transform_train = transforms.Compose([
            transforms.RandomCrop(32, padding=4),
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            normalize,
            ])

    transform_test = transforms.Compose([
            transforms.ToTensor(),
            normalize])
    training_set = datasets.CIFAR10(root="./data", train=True,
                                                download=True, transform=transform_train)
    training_sampler = torch.utils.data.distributed.DistributedSampler(training_set,num_replicas=num_nodes, rank=rank, shuffle=True, seed=0, drop_last=False)
    train_loader = torch.utils.data.DataLoader(training_set,
                                                    num_workers=2,
                                                    batch_size=batch_size,
                                                    sampler=training_sampler,
                                                    pin_memory=True)
    test_set = datasets.CIFAR10(root="./data", train=False,
                                download=True, transform=transform_test)
    #test_sampler = torch.utils.data.distributed.DistributedSampler(test_set,num_replicas=num_nodes, rank=rank, shuffle=True, seed=0, drop_last=False)
    test_loader = torch.utils.data.DataLoader(test_set,
                                              num_workers=2,
                                              batch_size=batch_size,
                                              shuffle=False,
                                              pin_memory=True)
    training_criterion = torch.nn.CrossEntropyLoss().to(device)

    model = mdl.VGG11()
    model = DistributedDataParallel(model)
    model.to(device)
    optimizer = optim.SGD(model.parameters(), lr=0.1,
                          momentum=0.9, weight_decay=0.0001)
    # running training for one epoch
    for epoch in range(1):
        train_model(model, train_loader, optimizer, training_criterion, epoch, args)
        test_model(model, test_loader, training_criterion)

if __name__ == "__main__":
    main()
