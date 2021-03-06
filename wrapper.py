from __future__ import print_function

import pickle

import numpy as np
import torch
from torch import optim

from model import TriMap
from triplets import generate_triplets


class Wrapper(object):

    def __init__(self, config):
        self.config = config
    
    def embed(self, embed_init=None,
              return_seq=False):

        num_triplets = self.triplets.shape[0]
        
        out_shape = [self.num_examples, self.config.out_dim]
        Yinit = embed_init or 0.0001 * np.random.normal(size=out_shape)
        
        if torch.cuda.is_available():
            model = TriMap(self.triplets, self.weights,
                           out_shape=out_shape, embed_init=Yinit,
                           use_cuda=True)
            model.cuda()
        
        else:
            model = TriMap(self.triplets, self.weights,
                           out_shape=out_shape, embed_init=Yinit)

        lr = 1000.0 if self.config.lr is None else self.config.lr
        eta = lr * self.num_examples / num_triplets

        # full-batch gradient descent
        if self.config.optimizer == 'gd':
            optimizer = optim.SGD(model.parameters(), lr=eta)
        elif self.config.optimizer == 'gd-momentum':
            optimizer = optim.SGD(model.parameters(), lr=eta, momentum=.9)
        elif self.config.optimizer == 'rmsprop':
            optimizer = optim.RMSprop(model.parameters(), lr=eta)
        elif self.config.optimizer == 'adam':
            optimizer = optim.Adam(model.parameters(), lr=eta)

        tol = 1e-7
        C = np.inf
        # best_C, best_Y = np.inf, None

        t = self.config.t
        if self.config.anneal_scheme != 1:
            tmin = self.config.t
            tmax = self.config.t_max

        if return_seq:
            Y_seq = []

        print('[*] Training on %s using %s with anneal scheme %d' % (
              'GPU' if torch.cuda.is_available() else 'CPU',
              self.config.optimizer, self.config.anneal_scheme))

        for itr in range(self.config.num_iters):
            old_C = C

            if self.config.anneal_scheme == 1:
                # scale t linearly by fifths after first half of training
                if itr >= self.config.num_iters / 2.0:
                    if itr % int(self.config.num_iters / 10.0) == 0:
                        t += (tmax - tmin) / 5.0

            elif self.config.anneal_scheme == 2:
                # scale t linearly throughout training
                t += (tmax - tmin) / self.config.num_iters
 
            loss, num_viol = model(t=t)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            C = loss.data.cpu().numpy()[0]
            viol = float(num_viol.data[0]) / self.triplets.shape[0]
            
            if self.config.optimizer[:2] == 'gd':
                if C > old_C + tol:
                    eta *= 0.9
                else:
                    eta *= 1.01
                optimizer.param_groups[0]['lr'] = eta

            if return_seq:
                Y = model.get_embeddings()
                Y_seq.append(Y.copy())
            
            # if C < best_C:
            #     best_C = C
            #     best_Y = model.get_embeddings()

            if self.config.verbose and (itr+1) % self.config.print_every == 0:
                print('[{}/{}] Loss: {:3.3f} Triplet Error: {:.2%}'. \
                    format(itr+1, self.config.num_iters, C, viol))

        return Y_seq if return_seq else model.get_embeddings()
        # return Y_seq if return_seq else best_Y

    def load_triplets(self, path):
        with open(path, 'rb') as f:
            print('[*] Loading triplets from %s' % path)
            self.triplets, self.weights, self.num_examples = pickle.load(f)

    def generate_triplets(self, X, path=None):
        self.num_examples = X.shape[0]
        self.triplets, self.weights = generate_triplets(X, svd_dim=self.config.svd_dim, verbose=self.config.verbose)
        if path:
            print('[*] Saving generated triplets to %s' % path)
            with open(path, 'wb') as f:
                pickle.dump((self.triplets, self.weights, self.num_examples), f)

    def load_state(self, path):
        raise NotImplementedError
    
    def save_state(self, path):
        raise NotImplementedError
