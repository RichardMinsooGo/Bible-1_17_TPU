import tensorflow as tf
from tensorflow.keras.layers import Dense, Flatten, Conv2D, MaxPool2D, Dropout
from tensorflow.keras import Model, Sequential

from tensorflow.keras.utils import to_categorical
import numpy as np

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

print(tf.__version__)

import distutils
if distutils.version.LooseVersion(tf.__version__) <= '2.0':
    raise Exception('This notebook is compatible with TensorFlow 1.14 or higher, for TensorFlow 1.13 or lower please use the previous version at https://github.com/tensorflow/tpu/blob/r1.13/tools/colab/fashion_mnist.ipynb')

resolver = tf.distribute.cluster_resolver.TPUClusterResolver('grpc://' + os.environ['COLAB_TPU_ADDR'])
tf.config.experimental_connect_to_cluster(resolver)

# This is the TPU initialization code that has to be at the beginning.
tf.tpu.experimental.initialize_tpu_system(resolver)
print("All devices: ", tf.config.list_logical_devices('TPU'))

strategy = tf.distribute.experimental.TPUStrategy(resolver)

learning_rate = 0.001

## MNIST Dataset #########################################################
# mnist = tf.keras.datasets.mnist
# class_names = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
##########################################################################

## Fashion MNIST Dataset #################################################
mnist = tf.keras.datasets.fashion_mnist
class_names = ['T-shirt/top', 'Trouser', 'Pullover', 'Dress', 'Coat', 'Sandal', 'Shirt', 'Sneaker', 'Bag', 'Ankle boot']
##########################################################################

(X_train, Y_train), (X_test, Y_test) = mnist.load_data()    

# Change data type as float. If it is unt type, it might cause error 
X_train = X_train / 255.
X_test  = X_test / 255.

# in the case of Keras or TF2, type shall be [image_size, image_size, 1]
# if it is RGB type, type shall be [image_size, image_size, 3]
# For MNIST or Fashion MNIST, it need to reshape
X_train = np.expand_dims(X_train, axis=-1)
X_test = np.expand_dims(X_test, axis=-1)
    
Y_train = to_categorical(Y_train, 10)
Y_test = to_categorical(Y_test, 10)    
    
batch_size = 1000
# 입력된 buffer_size만큼 data를 채우고 무작위로 sampling하여 새로운 data로 바꿉니다.
# 완벽한 셔플링을 위해서는 데이터 세트의 전체 크기보다 크거나 같은 버퍼 크기가 필요합니다.
# 만약 작은 데이터수보다 작은 buffer_size를 사용할경우,
# 처음에 설정된 buffer_size만큼의 data안에서 임의의 셔플링이 발생합니다.
shuffle_size = 100000

train_ds = tf.data.Dataset.from_tensor_slices(
    (X_train, Y_train)).shuffle(shuffle_size).batch(batch_size)
test_ds = tf.data.Dataset.from_tensor_slices(
    (X_test, Y_test)).batch(batch_size)

"""
def create_model():
    model = Sequential()
    
    model.add(Conv2D(filters=64, kernel_size=3, activation=tf.nn.relu, padding='SAME', 
                                  input_shape=(28, 28, 1)))
    model.add(MaxPool2D(padding='SAME'))
        
    model.add(Conv2D(filters=128, kernel_size=3, activation=tf.nn.relu, padding='SAME'))
    model.add(MaxPool2D(padding='SAME'))
    
    model.add(Flatten())
    model.add(Dense(128, activation=tf.nn.relu))
    model.add(Dropout(0.4))
    model.add(Dense(10, activation=tf.nn.softmax))
    
    return model

model = create_model()
"""
model = Sequential([
    Conv2D(filters=64, kernel_size=3, activation=tf.nn.relu, padding='SAME',input_shape=(28, 28, 1)),
    MaxPool2D(padding='SAME'),
    Conv2D(filters=128, kernel_size=3, activation=tf.nn.relu, padding='SAME'),
    MaxPool2D(padding='SAME'),
    Flatten(),
    Dense(128, activation='relu'),
    Dropout(0.2),
    Dense(10, activation='softmax')
])

model.summary()

optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)

checkpoint = tf.train.Checkpoint(cnn=model)

with strategy.scope():
    model = model

    @tf.function
    def loss_fn(model, images, labels):
        logits = model(images, training=True)
        loss = tf.reduce_mean(tf.keras.losses.categorical_crossentropy(
            y_pred=logits, y_true=labels, from_logits=True))    
        return loss   

    @tf.function
    def grad(model, images, labels):
        with tf.GradientTape() as tape:
            loss = loss_fn(model, images, labels)
        return tape.gradient(loss, model.variables)

    @tf.function
    def evaluate(model, images, labels):
        logits = model(images, training=False)
        correct_prediction = tf.equal(tf.argmax(logits, 1), tf.argmax(labels, 1))
        accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
        return accuracy

    @tf.function
    def train(model, images, labels):
        grads = grad(model, images, labels)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))

EPOCHS = 5

for epoch in range(EPOCHS):
    train_loss = 0.
    test_loss = 0.
    train_accuracy = 0.
    test_accuracy = 0.
    train_step = 0
    test_step = 0    
    
    for images, labels in train_ds:
        train(model, images, labels)
        #grads = grad(model, images, labels)                
        #optimizer.apply_gradients(zip(grads, model.variables))
        loss = loss_fn(model, images, labels)
        train_loss += loss
        acc = evaluate(model, images, labels)
        train_accuracy += acc
        train_step += 1
    train_loss = train_loss / train_step
    train_accuracy = train_accuracy / train_step
    
    for test_images, test_labels in test_ds:
        loss = loss_fn(model, test_images, test_labels)
        test_loss += loss
        acc = evaluate(model, test_images, test_labels)        
        test_accuracy += acc
        test_step += 1
    test_loss = test_loss / test_step
    test_accuracy = test_accuracy / test_step
    
    """
    print('Epoch:', '{}'.format(epoch + 1), 'loss =', '{:.8f}'.format(train_loss), 
          'train accuracy = ', '{:.4f}'.format(train_accuracy), 
          'test accuracy = ', '{:.4f}'.format(test_accuracy))
    """
    template = 'epoch: {:>5,d}, loss: {:>2.4f}, accuracy: {:>2.3f} %, test loss: {:>2.4f}, test accuracy: {:>2.3f} %'
    print (template.format(epoch+1,
                         train_loss,
                         train_accuracy*100,
                         test_loss,
                         test_accuracy*100))

print('Learning Finished!')



