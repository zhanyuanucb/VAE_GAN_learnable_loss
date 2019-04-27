# Import the basic packages
import mxnet as mx
from mxnet import nd, init, gluon, autograd, image
from mxnet.gluon import data as gdata, loss as gloss, nn
import numpy as np
import d2l
CTX = d2l.try_gpu()
import time
import matplotlib.pyplot as plt

# Import the DenseVAE and ResNet network classes
import sys
sys.path.insert(0, "./models")
from DenseVAE import DenseVAE
from ResNet import ResNet

# Prepare the training data and training data iterator
mnist = mx.test_utils.get_mnist()
train_features = nd.array(mnist['train_data'], ctx=CTX)
batch_size = 64
train_iter = gdata.DataLoader(train_features,
                                  batch_size,
                                 shuffle=True,
                                 last_batch='keep')


# Extract the training image's shape
_, n_channels, width, height = train_features.shape

# Instantiate the VAE model, then build the trainer and 
# initialize the parameters
n_latent = 2
n_hlayers = 10
n_hnodes = 400
dense_vae = DenseVAE(n_latent = n_latent,
                    n_hlayers = n_hlayers,
                    n_hnodes = n_hnodes,
                    n_out_channels = n_channels,
                    out_width = width,
                    out_height = height)
dense_vae.collect_params().initialize(mx.init.Normal(0.02), ctx=CTX)
vae_trainer = gluon.Trainer(dense_vae.collect_params(), 
                        'adam', 
                        {'learning_rate': .001})

# Instantiate the ResNet network, initialize it
# and build the trainer instance
resnet = ResNet(n_classes=1)
resnet.collect_params().initialize(mx.init.Normal(0.02), ctx=CTX)
resnet_trainer = gluon.Trainer(resnet.collect_params(),
                               'adam',
                               {'learning_rate': 0.01})

# The MXNet GAN implementation used a SigmoidBinaryCrossEntropyLOss
# I will write it out here and figure out what it means later
loss_func = gloss.SigmoidBinaryCrossEntropyLoss()

# Specify the directory to which validation images and training
# report (with training errors and time for each epoch) will be
# saved
result_dir = './results/images/DenseVAE_ResNet_on_MNIST/5_3_400_50/'
# Open a file to write to for training reports
readme = open(result_dir + 'README.md', 'w')
readme.write('Number of latent variables \t' + str(n_latent) + '\n\n')
readme.write('Number of hidden layers \t' + str(n_hlayers) + '\n\n')
readme.write('Number of hidden nodes per layer \t' + str(n_hnodes) + '\n\n')

n_epochs = 50
readme.write('Number of epochs trained \t' + str(n_epochs) + '\n\n')

for epoch in range(n_epochs):
    
    # Start recording trainig time
    start_time = time.time()
    # Initialize a list that records the average loss within
    # each batch
    vae_batch_losses = []
    resnet_batch_losses = []
    
    
    for batch_features in train_iter:
        batch_features = batch_features.as_in_context(CTX)
        batch_size = batch_features.shape[0]
        
        # Generate some real labels so the generated_features
        real_labels = nd.ones((batch_size,), ctx=CTX)
        fake_labels = nd.zeros((batch_size,), ctx=CTX)
        
        # First train the VAE to get a baseline generator
        with autograd.record():
            # Make a pass on "forward", which will get the KL_Div loss
            # and the logloss to be assigned into instance attributes
            dense_vae(batch_features)
            batch_kl_div_loss = dense_vae.KL_div_loss
            
            # Use the ResNet to compute a confidence score, then com
            generated_features = dense_vae.generate(batch_features)
            disc_scores = resnet(generated_features)

            # In training VAE, we want to maximize the closeness
            # of disc_scores to "all ones"
            # so we want to minimize its opposite
            batch_content_loss = loss_func(disc_scores, real_labels)
            
            # If it is the first epoch, ResNet is not ready for training
            # yet, so we use the pixel-by-pixel logloss for training
            # the VAE net
            if epoch == 0:
                batch_content_loss = dense_vae.logloss
                
            # Sum up the kl_div_loss and the content loss
            batch_loss = batch_content_loss + batch_kl_div_loss
            vae_batch_losses.append(nd.mean(batch_loss).asscalar())
            
        # Descent on gradient!
        batch_loss.backward()
        vae_trainer.step(batch_size)
        
    for batch_features in train_iter:
        batch_features = batch_features.as_in_context(CTX)
        batch_size = batch_features.shape[0]
        
        # Generate some real labels so the generated_features
        real_labels = nd.ones((batch_size,), ctx=CTX)
        fake_labels = nd.zeros((batch_size,), ctx=CTX)
        # Update the discriminator network
        with autograd.record():
            # First train with real labels and genuine images
            disc_scores = resnet(batch_features)
            # Compute the loss with real data
            real_loss = loss_func(disc_scores, real_labels)
            
            # Generate the fake images
            generated_features = dense_vae.generate(batch_features)
            # COmpute the results from fake images
            disc_scores = resnet(generated_features)
            # Compute the loss with the fake data
            fake_loss = loss_func(disc_scores, fake_labels)
            
            # Sum up the losses
            resnet_batch_loss = real_loss + fake_loss
            resnet_batch_losses.append(nd.mean(batch_loss).asscalar())
            
        # Descent on gradient
        resnet_batch_loss.backward()
        # There are 2 times the batch_size samples used in this epoch of 
        # training the ResNet
        resnet_trainer.step(batch_size * 2)
    
    # End of an epoch, counting batch losses and time used
    stop_time = time.time()
    epoch_vae_train_loss = np.mean(vae_batch_losses)
    epoch_resnet_train_loss = np.mean(resnet_batch_losses)
    time_consumed = stop_time - start_time
    
    # Generate the epoch report, write it to the report file and print it
    epoch_report_str = 'Epoch{}, VAE Training loss {:.5f}, ResNet Training loss {:.10f}, Time used {:.2f}'.format(epoch,
                                                                                                    epoch_vae_train_loss,
                                                                                                    epoch_resnet_train_loss,
                                                                                                    time_consumed)
    readme.write(epoch_report_str + '\n\n')
    print(epoch_report_str)
    
# Validation
img_arrays = dense_vae.generate(nd.array(mnist['test_data'], ctx=CTX)).asnumpy()

# Define the number of validation images to generate (and display in the README.md)
n_validations = 10

for i in range(n_validations):
    # Add a line that writes to the report to display the images
    readme.write('!['+str(i)+'](./'+str(i)+'.png)')
    img_array = img_arrays[i]
    fig = plt.figure()
    plt.imshow(img_array.reshape(width, height))
    plt.savefig(result_dir + str(i) + '.png')
    plt.close()
    
readme.close()

