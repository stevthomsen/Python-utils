#!/usr/bin/env python2.7
__author__ = "stthomse@cisco.com"
__copyright__ = "2017 Cisco Systems, Inc"

import paho.mqtt.client as mqtt
import sys

# Get the total number of args passed to the demo.py
total = len(sys.argv)

if total > 2:
  print("Error, must pass 0 or 1 args (" + str(total)
        + " passed)")
  exit(1)

if total == 1:
  message = "Default"
else:
  message = str(sys.argv[1])

mqttc = mqtt.Client("python_pub")
mqttc.connect("localhost", 1883)
mqttc.publish("ARTIM", message)
mqttc.loop(2) # timeout = 2s
