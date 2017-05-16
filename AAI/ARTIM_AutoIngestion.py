#!/usr/bin/env python2.7

from __future__ import print_function
__author__ = "stthomse@cisco.com"
__copyright__ = "2017 Cisco Systems, Inc"

"""
ARTIM Auto Ingestion, Python 2.7.

Script ASSUMES:
1. Script is run at bootup.
2. A AAI Configuration file is present on the BMC at a well-known
   location (virtauta default, /opt/virtuata/endpoint/AAI.cfg).

This script will:
Grab an xml config file from BMC fs
Parse the config file
Verify the config file for:
    1. The specifed ISO file exists
    2. The type of image to ingest
    3. The type of DB to produce
    4. The specified DB location is writable
    5. Only the above 4 elements are present in the config file
Copy the specified ISO to local storage
Start the Ingestion to local storage
Copy the created DB from local storage to specified location
Exit

"""

import traceback
import os
import sys
import subprocess
import getopt
import datetime
import re
import argparse as ap
import xml.etree.ElementTree
import uuid
import shlex
import time
import tempfile
from django.forms import URLField
#from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
#from django.core.urlresolvers import RegexURLResolver, Resolver404
import shutil
import wget

is_verbose = False
debug = False
localImage=None
myTempDir=None
myMountDir=None
dbLocation=None
localDB=None
debugNoCleanUp=False
looperUsed=None
heartbeatFileName = "/var/log/AAIdaemon/AAIdaemon.log"

# Function for debug printing
def debugPrint(message):
    global debug
    if debug:
        print (message)

# Function to set localImage (print it if debug is on)
def setLocalImage(myName):
    global localImage
    localImage=myName
    debugPrint('Setting localImage to ' + myName)

# Function to set localDB (print it if debug is on)
def setLocalDB(myName):
    global localDB
    localDB=myName
    debugPrint('Setting localDB to ' + myName)

# Function to dump contents of a file
def dumpFile(fname):
    with open(fname, 'r') as fin:
        print(fin.read())

# Validate url using django
def validate_url(url):
    url_form_field = URLField()
    try:
        url = url_form_field.clean(url)
    except ValidationError:
        return False
    return True

# Function to clean up /dev/mapper loop partitions
def cleanUpMapperLoops():
    for filename in os.listdir('/dev/mapper'):
        if filename.startswith('loop'):
            fullPath = os.path.join('/dev/mapper', filename)
            debugPrint ('Removing mapper loop ' + fullPath)
            rt = subprocess.call(["rm", "-rf", fullPath])
            if rt != 0:
                print ('Cannot remove ', fullPath)
                # Continue on to others not return(False)
    return(True)

# Function to write to heartbeat file
def writeHeartbeatFile(myString):
    global heartbeatFileName
    debugPrint('writeHeartbeatFile: ' + myString)
    try:
        heartbeatFile = open(heartbeatFileName, 'w')
    except:
        print('Error opening heartbeat file(' + heartbeatFileName + ')')
        cleanUp(22)
    try:
        heartbeatFile.write(myString + '\n')
    except:
        print('Error writing heartbeat file(' + heartbeatFileName + ')')
        cleanUp(23)
    try:
        heartbeatFile.close()
    except:
        print('Error closing heartbeat file(' + heartbeatFileName + ')')
        cleanUp(24)

def startHeartbeatDaemon():
    writeHeartbeatFile("Daemon started")

    # Start Heartbeat Daemon
    rt = subprocess.call(['python', '/usr/local/src/AAI/AAI_daemon.py',
                          'start'])
    if rt != 0:
        print('Heartbeat Daemon unable to start')
        cleanUp(131)

# Function to stop heartbeat daemon
def stopHeartbeatDaemon():
    writeHeartbeatFile("Stop") #Daemon will stop when this is seen
    # Stop Heartbeat Daemon
    #rt = subprocess.call(['python', '/usr/local/src/AAI/AAI_daemon.py',
                          #'stop'])
    #if rt != 0:
        #print('Heartbeat Daemon unable to stop')

# Function to cleanUp
def cleanUp(exitCode):
    global myMountDir
    debugPrint('Starting cleanUp')

    # Stop the heartbeat daemon
    stopHeartbeatDaemon()

    if debugNoCleanUp: # Used for debugging, so do not cleanUp
        print('No Clean Up is done')
        exit(0)
    try:
        os.chdir('/')
    except:
        print ('Cannot cd to / for cleanup')
        exit(101)

    # do any umount necessary
    if os.path.ismount(myMountDir):
        debugPrint ('Unmounting image')
        rt = subprocess.call(['umount', myMountDir])
        if not rt == 0:
            if debug:
                print ('Unmounting image failed')
                exit(102)
        else:
            debugPrint ('Unmounting image successful')

    # Use kpartx to delete partition image
    fullPath = os.path.join(myTempDir, localImage)
    command = 'kpartx -d ' + fullPath
    debugPrint(command)
    rt = subprocess.call(['kpartx', '-d', fullPath])
    if rt:
        print ('Could not kpartx delete on ', localImage, ' from ',
               image_name)
        print ('\treturned ', rt)

    # Clean up all mapper loops still existing
    cleanUpMapperLoops()
        
    # Remove the temp dir created
    try:
        shutil.rmtree(myTempDir)
        debugPrint('Successfully removed tree ' + myTempDir)
    except:
        print ('Cannot remove ', myTempDir)
        exit(103)
    exit(exitCode)

# Function to simulate touch
def touch(fname, times=None):
    fhandle = open(fname, 'a')
    try:
        os.utime(fname, times)
    finally:
        fhandle.close()

    return(0)

# Function for checking image existance
def imageExists(image_name):
    # Check if local and existant
    if os.path.isfile(image_name):
        debugPrint ('Local image exists: ' + image_name)
        return(True)
    # Check if url supplied and exists
    if validate_url(image_name):
        return(True)
    debugPrint ('Not valid URL: ', image_name)
    # Try other methods
        
    return(False)

# Function for copying image
def copyImage(image_name):
    # Check if local and existant
    if os.path.isfile(image_name):
        debugPrint ('Local image exists: ' + image_name)
        try:
            shutil.copy(image_name, '.')
            setLocalImage(os.path.basename(image_name))
            return(True)
        except IOError as e:
            print ('Error: image file not copied %s' % e)
            return(False)
        return(True)
    # Check if url supplied and exists
    if validate_url(image_name):
        try:
            filename = wget(image_name)
            debugPrint('Got: ' + filename + ' from ' + image_name)
            setLocalImage(filename)
            return(True)
        except:
            print ('Cannot retreive from url ', image_name)
            return(False)
    else:
        debugPrint ('Not valid URL: ' + image_name)
    # Try other methods
        
    return(False)

# Function for mounting image using correct partition
def mountImage(image_name):
    global myTempDir
    global localImage
    global myMountDir
    # First cleanup any old mapper loops
    cleanUpMapperLoops()
    # Use kpartx to partition image
    fullPath = os.path.join(myTempDir, localImage)
    command = 'kpartx -a ' + fullPath
    debugPrint(command)
    rt = subprocess.call(['kpartx', '-a', fullPath])
    if rt:
        print ('Could not kpartx on ', localImage, ' from ',
               image_name)
        print ('\treturned ', rt)
        return(False)
    # Search through /dev/mapper entries for loop*, mount them
    # and check for bin directory
    debugPrint('Looping the /dev/mapper')
    for filename in os.listdir('/dev/mapper'):
        if filename.startswith('loop'):
            # try Mounting it
            myPath = os.path.join('/dev/mapper', filename)
            command = 'mount ' + myPath + ' ' + myMountDir
            debugPrint(command)
            rt = subprocess.call(['mount', myPath, myMountDir])
            if rt != 0:
                print (command, 'failed with', rt)
            else:
                # Check if lib sbin opt etc bin etc. are visibls
                for sub in os.listdir(myMountDir):
                    if sub == "bin":
                        debugPrint('Got bin')
                        debugPrint('mountImage worked on ' + myPath)
                        return(True)

    return(False)

# Function to do ingestion
def doIngestion():
    global myMountDir
    global myTempDir
    global localImage
    global localDB

    # Have to cd to special directory to allow extractElfPages to work
    try:
        os.chdir("/opt/virtuata/endpoint/bin")
    except:
        print ('Cannot cd to /opt/virtuata/endpoint/bin')
        cleanUp(20)
    debugPrint ('Changed Dir to /opt/virtuata/endpoint/bin')

    # First extract the elf pages from mount point directory
    myPages = os.path.join(myTempDir, "pages.ubuntu-1")
    rt = subprocess.call(["/opt/virtuata/endpoint/bin/extractELFPages", "-d",
                          myMountDir, "-m", "user", "-o", myPages])
    if rt != 0:
        print ('extractELFPages failed on mount point directory')
        cleanUp(21)

    # Verify the result
    if not os.path.isfile(myPages):
        print ('Failed to create pages ' + myPages)
        cleanUp(22)
    debugPrint('Successfully created pages ' + myPages)

    # Create a per-VM directory to hold the page/oracle databases.
    (myBase, myExt) = localImage.split(".")
    try:
        os.chdir("/opt/virtuata/endpoint/db")
    except:
        print ('Cannot cd to /opt/virtuata/endpoint/db')
        cleanUp(23)
    debugPrint ('Changed Dir to /opt/virtuata/endpoint/db')
    if not os.path.isdir(myBase):
        debugPrint('Directory /opt/virtuata/endpoint/db/ ' + myBase
                   + 'does not exist')
        try:
            os.mkdir(myBase)
        except:
            print ('Failed to make dir ' + myBase)
            cleanUp(24)
    checkFile = myBase + 'zzz'
    touch(checkFile)
    if not os.path.isfile(checkFile):
        print ('DB location not writable: /opt/virtuata/endpoint/db/'
               + myBase)
        exit(113)
    debugPrint ('DB location is writable')
    try:
        os.remove(checkFile)
        debugPrint('Removed temp file for checking DB Location writable')
    except:
        print('Cannot remove temp file made for checking DB Location writable')
        exit(114)

    debugPrint('Made per-VM Directory ' + myBase)
    setLocalDB('/opt/virtuata/endpoint/db/' + myBase)

    # Create the page oracle and signature databases. For now, the
    # dbtype is 'raw', and the mode is 'user', as kernel ingestion does
    # not work with PV kernels.
    try:
        os.chdir("/opt/virtuata/endpoint/bin")
    except:
        print ('Cannot cd to /opt/virtuata/endpoint/bin')
        cleanUp(24)
    debugPrint('Changed Dir to /opt/virtuata/endpoint/bin')
    myDBDir = os.path.join("/opt/virtuata/endpoint/db", myBase)
    command = "./createPageDB -f " + myPages + " -d " + myDBDir + " -m user -s 8 -o 8 1600 3200"
    debugPrint('command')
    rt = subprocess.call(["./createPageDB", "-f", myPages,
                          "-d", os.path.join("../db", myBase),
                          "-m", "user", "-s", "8",
                          "-o", "8", "1600", "3200"])
    if rt != 0:
        print ('Create Pages DB Failed')
        cleanUp(25);
    myUserDB = os.path.join("../db", myBase, "pgoracle_user.db")
    if not os.path.isfile(myUserDB):
        print ('Failed to make User DB ' + myUserDB)
        cleanUo(26)
    debugPrint('Created User DB ' + myUserDB)
    myUserSig = os.path.join("../db", myBase, "pgsig_user.db")
    if not os.path.isfile(myUserDB):
        print ('Failed to make User DB ' + myUserSig)
        cleanUo(26)
    debugPrint('Created User Sig ' + myUserSig)

# Function to move DB stuff to final location
def moveDB():
    global dbLocation
    global localDB
    # Check if local and existant
    debugPrint('Checking if final DB (' + dbLocation + ') is local')
    if os.path.isdir(dbLocation):
        debugPrint('Local DB exists: ' + dbLocation)
        try:
            rt = subprocess.call(['cp', localDB + '/pgoracle_user.db',
                                  dbLocation])
            if rt != 0:
                print ('Error copying local DB (' + localDB + ') to '
                       + dbLocation)
                cleanUp(31)
        except:
            print ('Error: cp failed')
            cleanUp(32)
        try:
            rt = subprocess.call(['cp', localDB + '/pgsig_user.db',
                                  dbLocation])
            if rt != 0:
                print ('Error copying local DB sig (' + localDB + ') to '
                       + dbLocation)
                cleanUp(31)
        except:
            print ('Error: cp failed')
            cleanUp(33)
        debugPrint('Copied local DB (' + localDB + ') to ' + dbLocation)
        return(True)
    # Check if url supplied and exists
    debugPrint(dbLocation + ' is not local, check url')
    if validate_url(dbLocation):
        debugPrint('Final dbLocation is url (' + dbLocation + ')')
        return(True)
    debugPrint ('Not valid URL: ' + dbLocation)
    # Try other methods
    print('Cannot copy DB entries to ' + dbLocation)
    return(False)

#
# Print banner to output indicating the program info.
#
print ('***')
print ('  Cisco/CSPG/stthomse, ARTIM_AutoIngestion.py')
print ('  This utility auto launches ARTIM Ingestion based on xml config file.')
print ('***')

# Make sure log place is ready for daemon
if not os.path.isdir("/var/log/AAIdaemon"):
    try:
        os.makedirs("/var/log/AAIdaemon/", 0777)
        debugPrint("made dir /var/log/AAIdaemon")
    except:
        print('Cannot make dir /var/log/AAIdaemon')
        exit(112)
debugPrint("Directory for log (var/log/AAIdaemon) exists, check for writable")
checkFile = '/var/log/AAIdaemon/zzz'
touch(checkFile)
if not os.path.isfile(checkFile):
    print ('Log location not writable: /var/log/AAIdaemon')
    exit(113)
debugPrint ('Log location is writable')
try:
    os.remove(checkFile)
    debugPrint('Removed temp file for checking Log Location writable')
except:
    print('Cannot remove temp file made for checking Log Location writable')
    exit(1114)

# Start the heartbeat Daemon
startHeartbeatDaemon()

num_fetch_retries = 3
#
# Launch the GetAAIFile utility.
# 
# This utility takes NO command line options. 
# We have hardcoded the file name to AAI-Config.xml
# TODO: need to bottom out on err code from this utility and handle it. 
print ('\n**Execute the GetAAIFile utility to fetch AAI Config file.')
writeHeartbeatFile("Get Config File")
while num_fetch_retries:
    rt = subprocess.call('./GetAAIFile.py')
    if rt != 0:
        num_fetch_retries -= 1
    else:
        break

# Confirm that we got our Config file.
if not os.path.isfile('/tmp/AAI-Config.xml'):
    print ('Error: AAI Config file not retrieved.')
    exit(1)
debugPrint ('Got Config file')
writeHeartbeatFile("Got Config File")

# Make temp dir to do all of our work in and cd to it
try:
    myTempDir = tempfile.mkdtemp()
except:
    print ('Cannot create tempdir')
    exit(2)
debugPrint ('Created temp dir: ' + myTempDir)
try:
    os.chmod(myTempDir, 0777)
except:
    print ('Cannot chmod on tempdir')
    try:
        shutil.rmtree(myTempDir)
    except:
        print ('Cannot rmtree ontemp dir')
    cleanUp(3)
try:
    os.chdir(myTempDir)
except:
    print ('Cannot cd to temp dir')
    cleanUp(4)
debugPrint ('Changed Dir to ' + myTempDir)
writeHeartbeatFile("Temp Location Readied")

#
# Copy the file over to current location.
#
try:
    shutil.copy2('/tmp/AAI-Config.xml', myTempDir)
except IOError as e:
    print ('Error: AAI Config file not copied %s' % e)
    cleanUp(5)
debugPrint ('Config file copied to cwd')

#
#  Parse the AAI-Config.xml which we got from the GetAAIFile call above.
#
#  key :: pair format
#   image_name e.g. ubuntu-14.04.5-server-amd64.iso
#   os_type e.g. Linux
#   db_type e.g. text
#   db_location e.g. AAI.db
#
print ('**Parse the AAI-Config.xml blob')
writeHeartbeatFile("Parse config file")
try:
    tree = xml.etree.ElementTree.parse('AAI-Config.xml')
except:
    print('Cannot parse AAI-Config.xml')
    cleanUp(6)
debugPrint('Successfully parsed AAI-Config.xml') 
root = tree.getroot()
if debug:
    xml.etree.ElementTree.dump(root)
for configuration in root.findall('configuration'):
    image_name = configuration.find('image_name').text
    os_type = configuration.find('os_type').text
    db_type = configuration.find('db_type').text
    dbLocation = configuration.find('db_location').text

debugPrint ('Sampling of data passed via xml file...')
debugPrint ('\t' + image_name + ' ' + os_type + ' ' + db_type
            + ' ' + dbLocation)
debugPrint ('\n')
writeHeartbeatFile("Checking validity of config data")

# Check if os_type is valid
if not "Windows" == os_type:
    if not "Linux" == os_type:
        if not "other" == os_type:
            print ('Invalid OS type: ', os_type)
            cleanUp(6)
debugPrint ('OS type is valid')

# Check if DB type is valid
if not "text" == db_type:
    if not "other" == db_type:
        print ('Invalid DB type: ', db_type)
        cleanUp(7)
debugPrint ('DB type is valid')

# Check if image exists
if not imageExists(image_name):
    cleanUp(8)
debugPrint ('image exists')

# Check if DB location is directory
if os.path.isdir(dbLocation):
    debugPrint('DB location is already a directory')
else:
    if not os.path.exists(dbLocation):
        # Does not exist, so see if can create it
        try:
            os.mkdir(dbLocation)
            os.chmod(dbLocation, 0777) # Make it explicit
        except:
            print('Cannot make directory for DB location('
                  + dbLocation + ')')
            exit(9)
    else:
        print('Specified DB location already exists not as a directory')
        print('\t' + dbLocation)
        exit(10)

# Check if DB location is writable
checkFile = os.path.join(dbLocation, 'zzz')
touch(checkFile)
if not os.path.isfile(checkFile):
    print ('DB location not writable: ', dbLocation)
    exit(11)
debugPrint ('DB location is writable')
try:
    os.remove(checkFile)
    debugPrint('Removed temp file for checing DB Location writable')
except:
    print('Cannot remove temp file made for checing DB Location writable')
    exit(12)
writeHeartbeatFile("Config data is valid")

# copy the specified to local storage
writeHeartbeatFile("Copy image to temp location")
if not copyImage(image_name):
    exit(13)
print ('AAI image file copied')

print ('AAI local image is ', localImage)

# Mount the image, since already in temp dir create dir to mount
writeHeartbeatFile("Mounting image")
try:
    os.mkdir('mountDir')
    myMountDir = os.path.join(myTempDir, 'mountDir')
except:
    print ('Cannot make mounting dir')
if not mountImage(image_name):
    print ('Cannot mount ', image_name, ' properly (no bin exists)')
    cleanUp(14)

# Time to ingest
debugPrint('Mount work, time to ingest')
writeHeartbeatFile("Ingestion started")
doIngestion()
writeHeartbeatFile("Ingestion done")

# Move DB stuff to final directory
debugPrint('Ingestion done, time to move DB to final locationo')
moveDB()

writeHeartbeatFile("Cleanup")
cleanUp(0)

# Stop the heartbeat daemon just in case, should have been done already
stopHeartbeatDaemon()

