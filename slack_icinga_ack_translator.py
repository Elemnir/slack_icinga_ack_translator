#!/usr/bin/env python35
"""
    slack_icinga_ack_translator
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This service utilizes Bottle and Requests to form a shim layer 
    translating Slack Slash Command out-going webhooks into Icinga 
    Problem Acknowledgement API calls. Primarily so that admines may
    acknowledge issues remotely without requiring them to first fully 
    authenticate to the Icinga web client.
"""

__author__      = 'Adam Howard'
__credits__     = ['Adam Howard', 'Stephen Milton']
__license__     = 'BSD 3-Clause'

import base64
import json
import logging
import os
import shlex

import bottle
import requests

BOTTLE_PORT = int(os.getenv('BOTTLE_PORT', 5668))
ICINGA_HOST = os.getenv('ICINGA_HOST', 'https://localhost:5665')
ICINGA_USER = os.getenv('ICINGA_USER', 'root')
ICINGA_PASS = os.getenv('ICINGA_PASS', '')
SLACK_API_TOKEN = os.getenv('SLACK_API_TOKEN', '')
LOGGING_PATH = os.getenv('LOGGING_PATH', '/var/log/icinga/slack_ack_translator.log')

app = bottle.Bottle()
logging.basicConfig(
    filename=LOGGING_PATH, 
    format='[%(asctime)s] %(levelname)s [%(module)s:%(lineno)d] %(message)s',
    level=logging.INFO,
)


@app.post('/')
def icinga_middleware_handler():
    addr = bottle.request.remote_addr
    user = bottle.request.forms.get('user_name', 'icingaadmin')
    text = bottle.request.forms.get('text', '')
    cmd = shlex.split(text)

    # Check for the Slack API Token
    if bottle.request.forms.get('token','') != SLACK_API_TOKEN:
        logging.warning('%s - Invalid Slack API Token.', addr)
        bottle.abort('403', 'Invalid Slack API Token.')
    
    # Parse the command and determine the host or service to target
    if len(cmd) == 3:
        target = "type=Service&service={0}!{1}".format(cmd[0], cmd[1])
    elif len(cmd) == 2:
        target = "type=Host&host={0}".format(cmd[0])
    else:
        logging.info('%s - %s: Invalid Command: %s', addr, user, text)
        return "Usage: `/ack host [service] \"Comment ...\"`"
    
    # Log the user's command, regardless of whether or not it works
    logging.info('%s - %s: %s', addr, user, text)

    # Make a POST request to the Icinga API filtering using the target
    url = ICINGA_HOST  + "/v1/actions/acknowledge-problem?" + target
    r = requests.post(url, verify=False, auth=(ICINGA_USER, ICINGA_PASS), 
        headers={
            'Accept': 'application/json'
        }, json={ 
            'author': bottle.request.forms.get('user_name', 'icingaadmin'),
            'comment': cmd[-1].strip('"'),
            'notify': True
        }
    )

    # If the command failed, log it and inform the user
    if r.status_code < 200 or r.status_code > 300:
        logging.error('Icinga returned error %s: %s', r.status_code, r.text)
        return 'Icinga returned error {0}: {1}'.format(r.status_code, r.text)
    
    # Otherwise the request was a success, and Icinga should handle notifying
    # the Slack channel for us. Return an empty 200 - OK response to the user.
    return ""


if __name__ == "__main__":
    bottle.run(app, host='0.0.0.0', port=BOTTLE_PORT, debug=True)
