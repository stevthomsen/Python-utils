#!/usr/bin/env python2.7

#
# This script will verify the supplied email is valid

import dns
import sys
import validate_email
from validate_email import validate_email

DEBUG=False
EMailAddress=''
pname="is_valid_email.py"

def Usage():
    global pname
    print "Usage: %s email-address" % pname
    print "       or"
    print "Usage: %s -h" % pname

def main():
    global DEBUG
    global email
    global pname
    # get arg stuff -----------
    pname = str(sys.argv[0])
    total = len(sys.argv)
    if total != 2:
        Usage()
        exit(1)

    if str(sys.argv[1]) == '-h':
        Usage()
        exit(0)

    EMailAddress=str(sys.argv[1])

    print "Checking validity of email address %s" % EMailAddress
    is_valid = validate_email(EMailAddress, verify=True)

    if is_valid:
        print "%s is a valid EMail Address" % EMailAddress
        return(0)
    else:
        print "%s is an invalid EMail Address" % EMailAddress
        return(1)


if __name__ == '__main__':
    exit(0 if main() else 1)

