# Copyright 2017 Neural Networks and Deep Learning lab, MIPT
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import copy
import tensorflow as tf
import numpy as np
from collections import namedtuple
from tensorflow.contrib.layers import xavier_initializer
import os
import pickle


class NERTagger:
    """Neural Network model for Named Entity Recognition"""

    def __init__(self,
                 opt,
                 word_dict,
                 token_emb_dim=100,
                 char_emb_dim=25,
                 n_char_cnn_filters=25,
                 filter_width=3,
                 learning_rate=1e-3,
                 n_layers=4):
        """Assemble and initialize the model

                Args:
                    opt: options dictionary
                    word_dict: word dictionary
                    token_emb_dim: dimensionality of token embeddings
                    char_emb_dim: dimensionality of character embeddingas
                    n_char_cnn_filters: number of filter in character level CNN
                    filter_width: width of convolutional filters
                    learning_rate: learning rate
                    n_layers: number of convolutional layers
        """
        tf.reset_default_graph()
        seed = opt.get('random_seed')
        np.random.seed(seed)
        tf.set_random_seed(seed)
        self.token_emb_dim = token_emb_dim
        self.char_emb_dim = char_emb_dim
        self.n_char_cnn_filters = n_char_cnn_filters
        self.opt = copy.deepcopy(opt)
        vocab_size = len(word_dict)
        char_vocab_size = len(word_dict.char_dict)
        tag_vocab_size = len(word_dict.labels_dict)
        x_w = tf.placeholder(dtype=tf.int32, shape=[None, None], name='x_word')
        x_c = tf.placeholder(dtype=tf.int32, shape=[None, None, None], name='x_char')
        y_t = tf.placeholder(dtype=tf.int32, shape=[None, None], name='y_tag')

        # Learning stuff
        glob_step = tf.Variable(0, trainable=False)
        lr = tf.train.exponential_decay(learning_rate, glob_step, decay_steps=1024, decay_rate=0.5, staircase=True)


        # Load embeddings
        w_embeddings = np.random.randn(vocab_size, token_emb_dim).astype(np.float32) / np.sqrt(token_emb_dim)
        c_embeddings = np.random.randn(char_vocab_size, char_emb_dim).astype(np.float32) / np.sqrt(char_emb_dim)
        w_embeddings = tf.Variable(w_embeddings, name='word_emb_var', trainable=True)
        c_embeddings = tf.Variable(c_embeddings, name='char_emb_var', trainable=True)

        # Word embedding layer
        w_emb = tf.nn.embedding_lookup(w_embeddings, x_w, name='word_emb')
        c_emb = tf.nn.embedding_lookup(c_embeddings, x_c, name='char_emb')

        # Character embedding network
        with tf.variable_scope('Char_Emb_Network'):
            char_filter_width = 3
            char_conv = tf.layers.conv2d(c_emb,
                                         n_char_cnn_filters,
                                         (1, char_filter_width),
                                         padding='same',
                                         name='char_conv')
            char_emb = tf.reduce_max(char_conv, axis=2)

        wc_features = tf.concat([w_emb, char_emb], axis=-1)

        # Cutdown dimensionality of the network via projection
        # units = tf.layers.dense(wc_features, 50, kernel_initializer=xavier_initializer())
        units = wc_features

        units, auxilary_outputs = self.cnn_network(units, n_layers, filter_width)

        logits = tf.layers.dense(units, tag_vocab_size, name='Dense')
        ground_truth_labels = tf.one_hot(y_t, tag_vocab_size, name='one_hot_tag_indxs')
        loss_tensor = tf.losses.softmax_cross_entropy(ground_truth_labels, logits)
        padding_mask = tf.cast(tf.not_equal(x_w, word_dict[word_dict.null_token]), tf.float32)
        loss_tensor = loss_tensor * padding_mask
        loss = tf.reduce_mean(loss_tensor)

        self.loss = loss
        self.train_op = tf.train.AdamOptimizer(lr).minimize(loss)

        self.sess = tf.Session()
        self.word_dict = word_dict
        self.x = x_w
        self.xc = x_c
        self.y_ground_truth = y_t
        self.y_predicted = tf.argmax(logits, axis=2)
        if self.opt.get('pretrained_model'):
            self.load(self.opt.get('pretrained_model'))
        else:
            self.sess.run(tf.global_variables_initializer())

    def cnn_network(self, units, n_layers, filter_width):
        """Assemble Convolutional neural network

        Args:
            units: input units to be convolved with kernels
            n_layers: number of layers
            filter_width: width of the filter (kernel)

        Returns:
            units: output units of the CNN
            auxiliary_outputs: auxiliary outputs from every layer
        """
        n_filters = units.get_shape().as_list()[-1]
        auxiliary_outputs = []
        for n_layer in range(n_layers):
            units = tf.layers.conv1d(units,
                                     n_filters,
                                     filter_width,
                                     padding='same',
                                     name='Layer_' + str(n_layer),
                                     activation=None,
                                     kernel_initializer=xavier_initializer())
            auxiliary_outputs.append(units)
            units = tf.nn.relu(units)
        return units, auxiliary_outputs

    def train_on_batch(self, x, xc, y):
        """Perform one step of training

        Args:
            x: tokens batch indices 2-D
            xc: character batch indices 3-D
            y: tags batch indices 2-D

        Returns:
            loss: value of loss for the current train step
        """
        loss, _ = self.sess.run([self.loss, self.train_op], feed_dict={self.x: x, self.xc: xc, self.y_ground_truth: y})
        return loss

    def eval(self, x, y):
        """Evaluate loss function for given tokens and tags

        Args:
            x: tokens batch (array of indices)
            y: tags batch (array of indices)

        Returns:
            loss: mean loss for batch
        """
        loss = self.sess.run(self.loss, feed_dict={self.x: x, self.y_ground_truth: y})
        return loss

    def predict(self, x, xc):
        """Predict tags for given batch

        Args:
            x: tokens batch indices 2-D
            xc: character batch indices 3-D

        Returns:
            y: predicted tags batch indices 2-D
        """
        y = self.sess.run(self.y_predicted, feed_dict={self.x: x, self.xc: xc})
        return y

    def save(self, file_path):
        """Save the model parameters

        Args:
            file_path: saving path of the model
        """
        saver = tf.train.Saver()
        print('saving path ' + os.path.join(file_path, 'model.ckpt'))
        saver.save(self.sess, os.path.join(file_path, 'model.ckpt'))

    def load(self, file_path):
        """Load the model parameters

            Args:
                file_path: loading path of the model
        """
        saver = tf.train.Saver()
        print('loading path ' + os.path.join(file_path, 'model.ckpt'))
        saver.restore(self.sess, os.path.join(file_path, 'model.ckpt'))

    def shutdown(self):
        """Reset the model"""
        tf.reset_default_graph()
