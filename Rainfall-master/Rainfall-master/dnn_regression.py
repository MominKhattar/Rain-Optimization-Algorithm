#!/usr/bin/env python

"""
Script for deep neural network regression to predict rainfall amount.

CS 273A
In-class Kaggle
"""

# Standard library imports
import argparse
import errno
import os
import sys

# Third party imports
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error
from sklearn.cross_validation import train_test_split
import pylearn2
import pylearn2.monitor
import pylearn2.train
import pylearn2.models.mlp
import pylearn2.training_algorithms.sgd
import pylearn2.training_algorithms.bgd
import pylearn2.termination_criteria
import pylearn2.train_extensions.best_params
import pylearn2.costs.cost
import pylearn2.costs.mlp
import pylearn2.cross_validation.subset_iterators
import pylearn2.costs.mlp.dropout
import pylearn2.utils.serial
from pylearn2.datasets.dense_design_matrix import DenseDesignMatrix
from theano import function

def predict(x, model):
    X = model.get_input_space().make_theano_batch()
    Y = model.fprop(X)
    f = function([X], Y)
    return f(x)

def initialize_dnn(dataset_tr, dataset_va, output_dir, activation_function, num_features, 
    num_hidden_layers, num_hidden_nodes_per_layer, learning_rate, minibatch_size, 
    stdev, dropout, gaussian):

    output_dir = output_dir + "/"

    if activation_function=='relu':
        hidden_layer = pylearn2.models.mlp.RectifiedLinear
    elif activation_function=='tanh':
        hidden_layer = pylearn2.models.mlp.Tanh
    elif activation_function=='sig':
        hidden_layer = pylearn2.models.mlp.Sigmoid

    layers = list()
    for l in xrange(num_hidden_layers):
        layers.append(hidden_layer(layer_name='h'+str(l), dim=num_hidden_nodes_per_layer,
        istdev=stdev))

    if gaussian:
        print 'Using Gaussian layer'
        channelmonitor="valid_y_mse"
        layers.append(pylearn2.models.mlp.LinearGaussian(layer_name='y', dim=1, irange=0.005, 
            init_bias=0.6, 
            init_beta=np.array([0.8]),
            min_beta=0.5, max_beta=100., beta_lr_scale=1.))
    else:
        channelmonitor="train_objective"
        layers.append(pylearn2.models.mlp.Linear(layer_name='y', dim=1, istdev=stdev))

    num_layers = len(layers)
    
    model = pylearn2.models.mlp.MLP(layers=layers, nvis=num_features)
    
    costFunction = pylearn2.costs.mlp.Default()
    if dropout:
        costFunction = pylearn2.costs.mlp.dropout.Dropout(default_input_include_prob=0.5,  default_input_scale=1/0.5,
            input_include_probs={'h0':0.9}, input_scales={'h0':1/0.9})

    cost = pylearn2.costs.cost.SumOfCosts(costs=[costFunction])

    criteria = [pylearn2.termination_criteria.MonitorBased(channel_name=channelmonitor,
        prop_decrease=0., N=10),
        pylearn2.termination_criteria.EpochCounter(max_epochs=122)]
   
    algorithm = pylearn2.training_algorithms.sgd.SGD(batch_size=minibatch_size, 
        learning_rate=learning_rate,
        monitoring_dataset={'train':dataset_tr, 'valid':dataset_va},
        cost=cost,
        termination_criterion=pylearn2.termination_criteria.And(
            criteria=criteria))

    extensions = [pylearn2.train_extensions.best_params.MonitorBasedSaveBest(
        channel_name=channelmonitor,
        save_path=output_dir+ "NNModel_best.pkl")]

    trainer = pylearn2.train.Train(dataset=dataset_tr, model=model,
        algorithm=algorithm, extensions=extensions,
        save_path=output_dir+ "NNModel.pkl", save_freq=1)

    return trainer, model

def scale_data(Xtr, Xte):
    s = StandardScaler()
    s.fit(Xtr)
    np.copyto(Xtr,s.transform(Xtr))
    np.copyto(Xte,s.transform(Xte))
    return s

def load_data(input_dir, useX1andX2):
    input_dir = input_dir + "/"
    Xtr = np.loadtxt(input_dir + 'kaggle.X1.train.txt.gz',delimiter=',',dtype='float32')    
    Xte = np.loadtxt(input_dir + 'kaggle.X1.test.txt.gz',delimiter=',',dtype='float32')
    Ytr = np.loadtxt(input_dir + 'kaggle.Y.train.txt.gz',dtype='float32')    
    if useX1andX2:
        X2tr = np.loadtxt(input_dir + 'kaggle.X2.train.txt.gz',delimiter=',',dtype='float32')
        X2te = np.loadtxt(input_dir + 'kaggle.X2.test.txt.gz',delimiter=',',dtype='float32')
        Xtr = np.concatenate((Xtr, X2tr), axis=1)
        Xte = np.concatenate((Xte, X2te), axis=1)    
    return Xtr, Ytr, Xte

def train(input_dir, output_dir, activation_function, num_hidden_layers, 
    num_hidden_nodes_per_layer, learning_rate, minibatch_size, stdev, 
    dropout, useX1andX2, gaussian, valid_size, random_seed):
    
    np.random.seed(random_seed)

    print 'Loading data'
    Xtr, Ytr, Xte = load_data(input_dir, useX1andX2)
    print 'Scaling data'
    s = scale_data(Xtr, Xte)

    Xtr, Xva, Ytr, Yva = train_test_split(Xtr, Ytr, test_size=valid_size)
    
    dataset_tr = DenseDesignMatrix(X=Xtr,y=Ytr.reshape(len(Ytr),1))
    dataset_va = DenseDesignMatrix(X=Xva,y=Yva.reshape(len(Yva),1))

    _, num_features = Xtr.shape

    trainer, model = initialize_dnn(dataset_tr, dataset_va, output_dir, 
        activation_function, num_features, num_hidden_layers, 
        num_hidden_nodes_per_layer, learning_rate, minibatch_size,
        stdev, dropout, gaussian)
    trainer.main_loop()

    best_model = pylearn2.utils.serial.load(output_dir+ "/NNModel_best.pkl")

    Ytr_pred = predict(Xtr, best_model)
    Yva_pred = predict(Xva, best_model)
    Yte_pred = predict(Xte, best_model)

    J_tr = mean_squared_error(Ytr_pred[:,0], Ytr)
    J_va = mean_squared_error(Yva_pred[:,0], Yva)
    
    print "Training MSE:", J_tr
    print "Validation MSE:", J_va

    print "Outputting predictions on test set"
    test_predictions_file = open(output_dir + "/predictions.csv", "w")
    test_predictions_file.write('ID,Prediction\n')
    for i in xrange(len(Yte_pred)):
        test_predictions_file.write(str(i+1) + "," + str(max(0,Yte_pred[i,0])) + "\n")
    test_predictions_file.close()

def make_argument_parser():
    """
    Creates an ArgumentParser to read the options for this script from
    sys.argv
    """
    parser = argparse.ArgumentParser(
    description="Train a deep network model for genome segmentation from a directory of input "
    "files, such as binarized ChromHMM training.",
    epilog='\n'.join(__doc__.strip().split('\n')[1:]).strip(),
    formatter_class=argparse.RawTextHelpFormatter)
    
    parser.add_argument('--inputdir', '-i', type=str, required=True,
    help='Directory containing input Kaggle training and test files.')
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-o", "--outputdir", type=str,
    help='The output directory. Will cause an error if the directory already exists.')
    group.add_argument("-oc", "--outputdirc", type=str,
    help='The output directory. Will overwrite if directory already exists.')
    
    parser.add_argument('--activation', '-a', action='store', choices=("tanh","relu","logistic"),
    default='relu',
    help='The activation function to use. relu, tanh, sig (default: relu).')
    
    parser.add_argument('--numhiddenlayers', '-l', type=int, default=1,
    help='The number of hidden layers (default: 1).')
    
    parser.add_argument('--numhiddennodesperlayer', '-k', type=int, default=100,
    help='The number of hidden nodes per layer (default: 100).')

    parser.add_argument('--minibatchsize', '-m', type=int, default=100,
    help='Minibatch size (default: 100).')

    parser.add_argument('--useX1andX2', '-u', action='store_true',
    help='If specified, use both X1 and X2 features. Otherwise, use only X1.')     

    parser.add_argument('--dropout', '-d', action='store_true',
    help='If specified, use dropout.')

    parser.add_argument('--learningrate', '-e', type=float, default=0.01,
    help='Learning rate (default: 0.01).')

    parser.add_argument('--randomseed', '-r', type=int, default=0,
    help='Random seed (default: 0).')

    parser.add_argument('--stdev', '-s', type=float, default=0.01,
    help='Random seed (default: 0.01).')

    parser.add_argument('--validsize', '-v', type=float, default=0.1,
    help='Fraction of training set to set aside as validation set. (default: 0.1).')

    parser.add_argument('--gaussian', '-g', action='store_true',
    help='If specified, use linear gaussian output layer.')

    return parser

if __name__ == "__main__":
    """
    See module-level docstring for a description of the script.
    """
    parser = make_argument_parser()
    args = parser.parse_args()

    if args.outputdir is None:
        clobber = True
        output_dir = args.outputdirc
    else:
        clobber = False
        output_dir = args.outputdir

    try:#adapted from DREME.py by T. Bailey
        os.makedirs(output_dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            if not clobber:
                print >> sys.stderr, ("output directory (%s) already exists "
                "but program was told not to clobber it") % (output_dir);
                sys.exit(1)
            else:
                print >> sys.stderr, ("output directory (%s) already exists "
                "so it will be clobbered") % (output_dir);

    train(args.inputdir, output_dir, args.activation, args.numhiddenlayers, 
        args.numhiddennodesperlayer, args.learningrate, args.minibatchsize, args.stdev, 
        args.dropout, args.useX1andX2, args.gaussian, args.validsize, args.randomseed)
