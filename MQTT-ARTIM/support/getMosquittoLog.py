#!/usr/bin/env python2.7

from __future__ import print_function
__author__ = "stthomse@cisco.com"
__copyright__ = "2017 Cisco Systems, Inc"

import traceback
import os
import sys
import time
import curses
import paho.mqtt.client as mqtt

global maxStatusLine
maxStatusLine = 1
global debug
debug = False

# Function for debug printing
def debugPrint(message):
    if debug:
        print (message)

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, rc):
  print("Connected with result code "+str(rc))
  # Subscribing in on_connect() means that if we lose the connection and
  # reconnect then subscriptions will be renewed.
  client.subscribe("ARTIM")
  client.subscribe("AAI")
  client.subscribe("SYSTEM")
  client.subscribe("log")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
  global maxStatusLine
  shortLine = "Topic: " + msg.topic + ' Message: ' + str(msg.payload)
  myLine = shortLine
  if len(shortLine) > maxStatusLine:
    maxStatusLine = len(shortLine)
  else:
    addSpaces = maxStatusLine - len(shortLine)
    debugPrint('Need to add ' + str(addSpaces) + ' spaces')
    debugPrint('Len is ' + str(len(myLine)))
    i = 0
    while i < addSpaces:
      myLine += ' '
      debugPrint('Adding space len is ' + str(len(myLine)))
      i = i + 1
  myLine += '\r'
  try:
    sys.stdout.write(myLine)
  except:
    print('Cannot write to stdout')
    exit(3)
  try:
    sys.stdout.flush()
  except:
    print('Cannot flush stdout')
    exit(4)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("10.128.249.64", 1883, 60)
print("press [CRTL-C] to stop")

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
client.loop_forever()
