#!/usr/bin/python


import argparse
import subprocess
import json
import re
import config
import collections
from datetime import datetime, timedelta
import time
from pprint import pprint

from slacker import Slacker
slack = Slacker(config.token)


option_age = ""
option_owner = None
option_protocol = 'slack'
option_ssm = None
option_stat = None

query_cache = {}
HOST="openbmc.gerrit"


def query(*args):

    COMMAND = """gerrit query \
    --format json --all-reviewers \
    --dependencies --current-patch-set -- \
    '%s'""" % " ".join(args)

    s = subprocess.Popen(["ssh", "%s" % HOST, COMMAND], 
                        shell=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)


    results = list(map(json.loads, s.stdout.read().splitlines()))
    del results[-1]

    for r in results:
        query_cache[r['id']] = r

    return results


def changes():
    args = ""
    if option_owner:
        args += " ( {0} )".format(option_owner)
    return query(args,
                 "status:open", "-is:draft", "-label:Code-Review=-2",
                 "-project:openbmc/openbmc-test-automation")


def change_by_id(change_id):
    if change_id in query_cache:
        return query_cache[change_id]
    c = query(change_id)
    if len(c):
        return c[0]
    return None


username_map = {
    'irc': {
        'jenkins-openbmc': "Jenkins",
        'williamspatrick': "stwcx",
    },
    'slack': {
        'amboar': "@arj",
        'anoo1': "@anoo",
        'bradbishop': "@bradleyb",
        'bjwyman': "@v2cib530",
        'cbostic': "@cbostic",
        'chinaridinesh': "@chinari",
        'charleshofer': "@charles.hofer",
        'dhruvibm': "@dhruvaraj",
        'dkodihal': "@dkodihal",
        'devenrao': "@devenrao",
        'geissonator': "@andrewg",
        'eddiejames': "@eajames",
        'gtmills': "@gmills",
        'jenkins-openbmc': "Jenkins",
        'JoshDKing': "@jdking",
        'lgon':"@lgonzalez",
        'mine260309': "@shyulei",
        'msbarth': "@msbarth",
        'mtritz': "@mtritz",
        'ojayanth': "@ojayanth",
        'ratagupt': "@ratagupt",
        'saqibkh': "@khansa",
        'shenki': "@jms",
        'spinler': "@spinler",
        'tomjoseph83': "@tomjoseph",
        'vishwabmc': "@vishwanath",
        'williamspatrick': "@iawillia",
    },
}


def map_username(user):
    return username_map[option_protocol].get(
        user[0], "[{0}: {1}]".format(user[0].encode('utf-8'), user[1].encode('utf-8')))


def map_approvals(approvals, owner):
    mapped = {}
    for a in approvals:
        approval_type = a['type']
        approval_owner = (a['by']['username'], a['by'].get('name'))
        approval_score = int(a['value'])

        if approval_type not in mapped:
            mapped[approval_type] = {}

        # Don't allow the owner to self-+1 on code-reviews.
        if approval_type == 'Code-Review' and approval_owner == owner and \
                approval_score > 0:
            continue

        mapped[approval_type][approval_owner] = approval_score

    return mapped


def map_reviewers(reviewers, owner):
    mapped = []
    for r in reviewers:
        if 'username' in r:
            reviewer_user = r['username']
        else:
            reviewer_user = "Anonymous-User"

        if 'name' in r:
            reviewer_name = r['name']
        else:
            reviewer_name = "Anonymous Coward"

        if reviewer_user == 'jenkins-openbmc':
            continue

        reviewer_username = (reviewer_user, reviewer_name)

        if reviewer_user == owner[0]:
            continue

        mapped.append(reviewer_username)

    return mapped


def reason(change):
    subject = change['subject']
    if change['owner'].get('name'): 
        real_name = change['owner'].get('name')
    else:
        real_name = change['owner']['username']
    owner = (change['owner']['username'], real_name)

    if 'allReviewers' in change:
        reviewers = map_reviewers(change['allReviewers'], owner)
    else:
        reviewers = []
    if 'approvals' in change['currentPatchSet']:
        approvals = map_approvals(change['currentPatchSet']['approvals'], owner)
    else:
        approvals = {}

    if len(reviewers) < 2:
        return ("{0} has added insufficient reviewers.", [owner], None)

    if ('Verified' in approvals):
        verified = approvals['Verified']
        scores = list(filter(lambda x: verified[x] < 0, verified))
        if len(scores):
            return ("{0} should resolve verification failure.", [owner], None)

    if ('Code-Review' not in approvals):
        return ("Missing code review by {0}.", reviewers, None)

    reviewed = approvals['Code-Review']
    rejected_by = list(filter(lambda x: reviewed[x] < 0, reviewed))
    if len(rejected_by):
        return ("{0} should resolve code review comments.", [owner], None)

    reviewed_by = list(filter(lambda x: reviewed[x] > 0, reviewed))
    if len(reviewed_by) < 2:
        return ("Missing code review by {0}.",
                set(reviewers) - set(reviewed_by), None)

    if ('Verified' not in approvals):
        return ("May be missing Jenkins verification ({0}).", [owner], None)

    if ('dependsOn' in change) and (len(change['dependsOn'])):
        for dep in change['dependsOn']:
            if not dep['isCurrentPatchSet']:
                return ("Depends on out of date patch set {1} ({0}).",
                        [owner], dep['id'])
            dep_info = change_by_id(dep['id'])
            if not dep_info:
                continue
            if dep_info['status'] != "MERGED":
                return ("Depends on unmerged patch set {1} ({0}).",
                        [owner], dep['id'])

    approved_by = list(filter(lambda x: reviewed[x] == 2, reviewed))
    if len(approved_by):
        return ("Ready for merge by {0}.", approved_by, None)
    else:
        return ("Awaiting merge review.", [], None)

send_to_slack = ['@andrewg',
                '@anoo',
                '@arj',
                '@bradleyb',
                '@cbostic',
                '@charles.hofer',
                '@chinari', 
                '@devenrao', 
                '@dkodihal',              
                '@dhruvaraj', 
                '@eajames', 
                '@gmills', 
                '@jms',
                '@khansa',               
                '@lgonzalez',  
                '@msbarth',
                '@ojayanth',
                '@ratagupt',
                '@spinler',
                '@tomjoseph',
                '@vishwanath',
                '@v2cib530']

def do_report(args):
    action_list = {}
    stat_list = {}
    oldest_action = {}
    oldest_review = {}
    for c in changes():
        patchCreatedOn = c['currentPatchSet']['createdOn']
        structTime = time.gmtime(patchCreatedOn)
        timePatchCreatedOn = datetime(*structTime[:6])
        timePatchCreatedOn -= timedelta(hours=5)
        dCTM = datetime.now() -  timePatchCreatedOn

        print("{0} - {1}".format(c['url'], c['id']))
        print(c['subject'].encode('utf-8'))
        (r, people, dep) = reason(c)
        people = ", ".join(map(map_username, people))
        print(r.format(people, dep))
        print("patch age:%s") % dCTM
        print("----")
        if "Depends on unmerged patch set" in r.format(people, dep):
            continue

        plist =  people.split(",")
        for p in plist:
            p = p.strip()
            message = "{0} - {1}".format(c['url'], c['id'].encode('utf-8')) 
            message = message + "\n" + c['subject'].encode('utf-8') + "\n" + r.format(people, dep) 
            message += "\npatch age:" + str(dCTM) + "\n----"
            action_list.setdefault(p, []).append(message)

            if "Missing code review" in message:
                if p not in oldest_action:
                    oldest_action.setdefault(p, []).append(patchCreatedOn)
                    oldest_action[p]= patchCreatedOn
                elif oldest_action[p] > patchCreatedOn:
                    oldest_action[p] = patchCreatedOn

    for slack_name, action_description in action_list.iteritems():
        print "~~~~"
        print slack_name

        total_actions_message = "Number of Actions: %d" % len(action_description)
        print total_actions_message
        
        if option_ssm and slack_name in send_to_slack:
            slack.chat.post_message(slack_name, total_actions_message)

        review_count = 0
        for description in action_description:
            if slack_name in send_to_slack:
                print description
            if "Missing code review" in description:
                review_count += 1

            if option_ssm and slack_name in send_to_slack:
#                print description
                slack.chat.post_message(slack_name, description)
        print "Number of Reviews: %d" % review_count

        if slack_name in oldest_action:
            structTime = time.gmtime(oldest_action[slack_name])
            timePatchCreatedOn = datetime(*structTime[:6])
            timePatchCreatedOn -= timedelta(hours=5)

            dCTM = datetime.now() -  timePatchCreatedOn
            print "Oldest Action: %s" % dCTM
        stat_list.setdefault(slack_name, []).append(review_count)
        

    message = ""
    for check_name in username_map['slack']:
        slack_name = username_map['slack'][check_name]
        if slack_name == 'Jenkins':
            continue
        if slack_name not in stat_list:
            message = message + "%s has [0] reviews, oldest patch age:\n" % (slack_name)


    sorted_stat_list =  sorted(stat_list.items(), key=lambda x: (x[1],x[0]))

    sorted_stat_list.remove(('', [0]))
    for s_name, cnt in sorted_stat_list:
        if s_name in username_map['slack'].values():
            dCTM = ""
            if s_name in oldest_action:
                structTime = time.gmtime(oldest_action[s_name])
                timePatchCreatedOn = datetime(*structTime[:6])
                timePatchCreatedOn -= timedelta(hours=5)
                dCTM = datetime.now() -  timePatchCreatedOn
            message = message + "%s has %s reviews, oldest patch age: %s\n" % (s_name, cnt, dCTM)


    print message
    if option_stat:
        print "sending stats to openbmcdev channel"
        slack.chat.post_message('#openbmcdev',message)
    

parser = argparse.ArgumentParser()
parser.add_argument('--owner', help='Change owner', type=str,
                    action='append')
parser.add_argument('--protocol', help='Protocol for username conversion',
                    type=str, choices=(username_map.keys()))
parser.add_argument('-sm', action='store_true',help='send slack message flag')
parser.add_argument('-stat', action='store_true',help='send statistics to slack flag')



subparsers = parser.add_subparsers()

report = subparsers.add_parser('report', help='Generate report')
report.set_defaults(func=do_report)

args = parser.parse_args()

if ('owner' in args) and args.owner:
    option_owner = " OR ".join(map(lambda x: "owner:" + x,
                                   args.owner))
if 'protocol' in args and args.protocol:
    option_protocol = args.protocol
if args.sm:
    option_ssm = 'True'
    print("will send messages to slack")
else:
    print("no slack messges will be sent")

if args.stat:
    option_stat = 'True'


if 'func' in args:
    args.func(args)
else:
    parser.print_help()
