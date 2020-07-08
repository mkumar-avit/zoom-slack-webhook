# Zoom-Slack-Webhook-Connector
# Purpose:  Sends webhook events from Zoom
# to Slack channel to notify Zoom users/admin
# of global changes to Zoom accounts or
# Zoom incidents that may degrade the service
# (separate statuspage channels exist, but this formats messages differently)
# Programmed by:   Maneesh Kumar initially for California Polytechnic State University

#Imported library must be maintained separately
import requests
#from pytz import timezone

#AWS Lambda Python Default libraries
import json
import os
import time

from datetime import datetime
from dateutil import tz


##@@@@TODO
#prep for SQS usage
#Plan is to retrieve and delete items from queue
# While API Gateways sends data to queue
#import boto3  


##GLOBAL VARIABLES
DBG_DISABLE = "disable"
DBG_TRUE = "true"
DBG_FALSE = "false"
DEBUG_MODE = DBG_DISABLE
date_format = '%m/%d/%Y %H:%M:%S %Z'
errorLog = []
token = ''
slackWebhookURI = ''
slackMsgHeader = ""
JWT_TOKEN = ""
groups = {}
tokenError = True


doNotDisplayList = ['Student']

jsonKeyIgnore = [
    "uuid",
    "id",
    "timezone",
    "account_id",
    "password"
]


slackHeader = {
    'hostname': "hooks.slack.com",
    'method': "POST",
    'path': "",
}

eventTypes = {
    "meeting": {
        "1": "Instant Meeting",
        "2": "Scheduled Meeting",
        "3": "Recurring Meeting with no fixed time.",
        "8": "Recurring Meeting with a fixed time."
    },
    "webinar": {
        "5": "Webinar",
        "6": "Recurring Webinar without a fixed time",
        "9": "Recurring Webinar with a fixed time."
    },
    "license": {
        "1": "Basic",
        "2": "Licensed",
        "3": "On-prem"
    }
}

#PII is personably identifiable data
#In the code the values are based on 
#group names.  If you don't want
#usernames, email addresses to display in slack
# for a particular Zoom group, enter it in the dictionary
# below.   The number represents Cal Poly's data security classification
pii =\
{
    'student':1\
}



eventDesc =\
    {
        "meeting.alert":
        {
            "name": "Meeting Alert",
            "emoji": ":exclamation:",
            "type": "meeting"
        },
        "meeting.started":
        {
            "name": "Meeting Started",
            "emoji": ":timer_clock:",
            "type": "meeting"
        },
        "webinar.created":
        {
            "name": "Webinar Created",
            "emoji": ":busts_in_silhouette:",
            "type": "webinar"
        },
        "webinar.alert":
        {
            "name": "Webinar Alert",
            "emoji": ":exclamation:",
            "type": "webinar"
        },
        "user.created":
        {
            "name": "User Created",
            "emoji": ":bust_in_silhouette:",
            "type": "license"
        },
        "account.settings_updated":
        {
            "name": "Account Setting Updated",
            "emoji": ":construction:"
        }
    }

apiURL =\
    {
        'users': 'https://api.zoom.us/v2/users',
        'groups': 'https://api.zoom.us/v2/groups',
        'scim2': 'https://api.zoom.us/scim2/Users/@',
        'plan': 'https://api.zoom.us/v2/accounts/@/plans/usage',
        'account':'https://api.zoom.us/v2/accounts/@',
        'roles':'https://api.zoom.us/v2/roles',
        'rolesList':'https://api.zoom.us/v2/roles/@/members'
    }


def log(msg):
    '''
    DEBUG_MODE enables program to
    send a slack message code block
    that contains all error messages
    for rapid debugging


    '''
    global errorLog

    if msg != "":
        print(msg)

        if DEBUG_MODE.lower() == DBG_DISABLE or DEBUG_MODE.lower() == DBG_TRUE:
            errorLog.append(msg)
            errorLog.append("\n")
    else:
        errorLog.clear()


def validate_event(msg, token):
    ''' Description:  This function validates the authorization token in the 
        message, not the JWT/OAuth token
    '''
    state = False

    try:
        if msg['headers']['authorization'] == token:
            state = True
            log('Authorization token validated for webhook event')
        else:
            log('Authorization tokens do not match.  Event Message ignored.')
    except Exception as e:
        log("Error validating event: {}".format(e))

    return state


def send_JWT_request(apiType, data=""):
    '''
        Description:  Sends request to Zoom to pull more detailed info
                      not available in webhook event payload 
         Parameters: apiType - string - references type of API request
                     if select the correct URL from the apiURL dict
                     data - string - represents string that is appended
                     to URL to pull specified data, i.e. user ID
          
    '''
    global tokenError
    response = ""
    respData = ""
    
    tokenError = True
    
    if JWT_TOKEN != '':
        url = apiURL[apiType]
        try:
            if '@' in url and data != "":
                url = url.replace("@", data)
        except Exception as e:
            log('Error in url replace: {}'.format(e))

        api = "{}".format(url)

        accessToken = 'Bearer ' + JWT_TOKEN
        authHeader = {'Authorization': accessToken}
        log("Sending JWT request for: {}".format(api))
       
        start = time.time()
        try:
            response = requests.get(url=api, headers=authHeader)
        except Exception as e:
            log('Send JWT Request {}, Response: {}, Error:{}'.format(api, response, e))     
        try:       
            roundtrip = time.time() - start
            status = response.status_code
            respTime = response.elapsed
            respData = response.json()
            log('JWT Request Response Processing Time:{} Roundtrip Time:{}, JWT Request Response: {},\n**RAW JWT Request DATA: {}'.format(
                respTime, roundtrip, response, respData))
            
          
            if status != 200 or 'code' in respData:
                log('Send JWT Token error: Code:{} Message:{}'.format(respData['code'],respData['message']))
                return "\n:coin-ce: Zoom account data cannot be retrieved: (JWT) {}\n".format(respData['message'])
            else:
                tokenError = False
        except Exception as e:
            log('Processing JWT Request {} error:{}'.format(api, e))
        
    return respData


def get_acct_info(acctID):

    rolesData = ""
    
    #acctInfo = send_JWT_request('account', acctID)
    #@ToDo further automation by searching list and roles
    
    rolesInfo = send_JWT_request('rolesList','0')
    try:
        rolesData = rolesInfo['members'][0]['email']
        return rolesData
    except Exception as e:
        print ('Error in rolesData:{}'.format(e))
        return rolesInfo
        
    


def get_user_group(group):
    global groups
    try:
        log('{} Group: {}'.format(group, groups))
        for groupItem in groups:
            if group['display'] == groups[groupItem]['id']:
                return groups[groupItem]['name']
                break
    except Exception as e:
        log('Error in getting group name: {}'.format(e))

    return group


def user_restricted(userID):
    # To Do cache scim2data to prevent multiple calls
    scim2data = get_user_scim2_data(userID)
    restricted = False

    for gItem in scim2data['groups']:
        group = '{} {}'.format(gItem['display'], group)
        if group in doNotDisplayList:
            restricted = True

    return doNotDisplay


def get_group_data():
    total_records = None
    response = None
    groupData = {}
    groups = ""

    try:
        groups = send_JWT_request('groups', data='')
    except Exception as e:
        log("Error getting group data: {}".format(e))
        groups = None

    if groups != None:
        try:
            total_groups = groups['total_records']
            # log('Number of groups found: {}'.format(total_groups))
        except Exception as e:
            log('Groups Count issue:{}'.format(e))
            total_groups = 0

        # loop through all pages and return user data
        for record in range(1, total_groups):
            try:
                gName = groups['groups'][record]['name']
            except Exception as e:
                log('No Group Name:'.format(e))
                gName = ''
            try:
                gID = groups['groups'][record]['id']
            except Exception as e:
                log('No Group ID:'.format(e))
                gID = ''

            try:
                groupData.update({gID: gName})
            except Exception as e:
                log('Error in storing group data: {}'.format(e))
    return groupData


def get_user_scim2_data(userID):
    # log('Checking SCIM2 Data for {}'.format(userID))
    # urn = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
    userInfo = ''

    try:
        userInfo = send_JWT_request('scim2', userID)
    except Exception as e:
        log("Error in userInfo:".format(e))
        userInfo = userID

    return userInfo
    
def scan_user_scim2_data(dataType, scim2data):
    '''
        Description:  pulls specific information from user scim2 data
                      and returns custom string concatenated from 
                      multiple data points.
        
    '''
    global doNotDisplayList
    

    def userInfoString(data, scim2data):
        userName = "No username"
        userType = "No user license type"
        if 'userName' in scim2data:
            userName = scim2data['userName']
        if 'userType' in scim2data:
            userType = scim2data['userType']
        
        if doNotDisplay != True:
            userString = "{}, {}, {} account ".format(userName, data, scim2data['userType'])    
        else:
            userString = "{}, {} account ".format(data, scim2data['userType'])
            
        return userString
        
    def pii_check(piiData,scim2data):
        '''
            Description:  processes user information to see if the data falls under
                          personaly identifiable data restriction classifications
             Parameters:  piiData - 
                          scim2Data - dictionary - containing scim2 user data from Zoom
        '''
        global doNotDisplay
        doNotDisplay = True
        if not piiData in doNotDisplayList:
            doNotDisplay = False
            
            if 'userName' in scim2data:
                scim2data['userName'] = 'PII Level 1 Restriction'
    
        return doNotDisplay
            
    noAssigned = "No assigned Zoom group"
    userInfo = ""
    group = ""

    if dataType in scim2data:
        if dataType == 'groups':
            if scim2data[dataType] == []:
                group = noAssigned
            else:
                for gItem in scim2data[dataType]:
                    group = '{} {}'.format(gItem['display'], group)
                    if pii_check(gItem['display'],scim2data) == True:
                        break
            userInfo = userInfoString(group, scim2data)
    else:
        group = noAssigned
        userInfo = userInfoString(group, scim2data)
        
    return [userInfo,doNotDisplay]
    
def eventProcessing(name, accountID):
    '''
        Description:  does transformation/calculations of specific data
                      based on zoom accountID
          Parameters: name - string to identify event being processed to pull
                      appropriate account information to be processed
                      accountID - Zoom accountID provided in webhook payload
    '''

    # if user created, check # of licenses in use and validate remaining licenses
    log('Event Processing: {} {}'.format(name, accountID))
    if name == "User Created":
        
        planInfo = send_JWT_request('plan', 'me')
        try:
            planLicenses = planInfo["plan_base"]["hosts"]
            planUsers = planInfo["plan_base"]["usage"]
            remaining = planLicenses - planUsers
            return "\nRemaining Licenses:  {} (out of {})\n".format(remaining, planLicenses)
        except Exception as e:
            return planInfo
    return ""


def statuspage_webhandler(event):
    '''
        Description:  Not fully implemented yet
    '''
    global slackMsgHeader
    global date

    eventTitle = "ZOOM SERVICE STATUS"
    eventEmoji = ":rotating_light"
    try:
        statusDate = event['datetime']
    except:
        statusDate = date.strftime(date_format)

    try:
        statusCurrent = event['current_status']
    except:
        statusCurrent = ""

    try:
        statusTitle = event['title']
    except:
        statusTitle = "Unknown"

    try:
        statusURL = event["incident_url"]
    except:
        statusURL = ""

    try:
        statusDetails = event['details']
    except:
        statusDetails = ""

    slackMsgHeader = "*_" + eventEmoji + eventTitle + \
        "_*" + ":\n" + date.strftime(date_format)


def zoom_webhandler(event):
    '''
        Description:  Processes webhook event and parses data from payload
                      and ultimately sends a formatted message to Slack
    '''
    global slackMsgHeader
    global zoomAccount
    global doNotDisplay

    zoomAccount = ""
    data = ""
    owner = ""

    objBody = {}
    try:
        objEvent = event
        objBody = json.loads(objEvent['body'])
    except Exception as e:
        try:
            objBody = objEvent['body']
        except:
            log("AWS Lambda error in JSON conversions: {}".format(e))

    evDesc = ""
    try:
        global eventDesc
        slackMsgHeader = "\n" + "*_" + ":exclamation:" + \
            "Notice" + "_*" + ":\n" + date.strftime(date_format)

        if 'account_id' in objBody or 'account_id' in objBody['payload']:
            try:
                zoomAccount = objBody['account_id']
            except:
                zoomAccount = objBody['payload']['account_id']
                
            owner = get_acct_info(zoomAccount)
            log("Zoom Account ID Discovered: {}, {}".format(zoomAccount, owner))
        if 'event' in objBody:
            evDesc = objBody['event']
            # log("Event Desc {}: {}".format(desc,eventDesc))
            try:
                if evDesc in eventDesc:
                    eventTxt = eventDesc[evDesc]['name']
                    eventEmoji = eventDesc[evDesc]['emoji']
                    eventData = eventProcessing(eventTxt, zoomAccount)
                    slackMsgHeader = "\n" + "*_" + eventEmoji + eventTxt + "_*" + \
                        ":\n" + date.strftime(date_format) + \
                        "{}".format(eventData)
            except Exception as e:
                log("Error in event description {}: {}".format(evDesc, e))
                slackMsgHeader = "{}\n{}".format(
                    slackMsgHeader, objBody['event'])

    except Exception as e:
        log('Notice: No event in message: {}'.format(e))

    objPayload = {}
    try:
        objPayload = objBody['payload']
        # log("objPayload {}: {}".format(type(objPayload),objPayload))

        if 'operator' in objPayload:
            extraData = ""
            if objPayload['operator'] == owner:
                objPayload['operator'] = 'Account Owner'
            if 'creation_type' in objPayload:
                extraData = " ({})".format(objPayload['creation_type'])
            slackMsgHeader = "{}\nUpdated By:  {}{}".format(
                slackMsgHeader, objPayload['operator'], extraData)
    except Exception as e:
        log("Error in getting JSON payload dict: {}".format(e))

    objData = {}
    try:
        objData = objPayload['object']
    except Exception as e:
        log("error in getting object {}: {}".format(type(objData), e))

    # If settings are update, can compare change and only show updated setting
    objDiff = None
    try:
        objDataOld = objPayload['old_object']
        # log("old_object Type:{}".format(type(objDataOld)))
        # objDiff = { d : objDataOld[d] for d in set(objDataOld) - set(objData) }
        objDiff = dict()
        for key in objDataOld:
            if (key in objData and objData[key] != objDataOld[key]):
                objDiff = {key: objData[key]}
                break
            else:
                objDiff = "A change has been made to the account, but the change is currently not documented in Zoom's API"
    except Exception as e:
        # log("API Isse:  No object_old data: {}".format(e))
        objDataOld = {}
        objDiff = None

    try:
        doNotDisplay = False
        data = ""
        userData = ""
        
        #Scan for user IDs first to identify PII classification level
        for item in objData:
            if item == 'id' and eventTxt == "User Created":
                try:
                    # Lookup ID to crossreference group membership
                    userDetails = get_user_scim2_data(objData[item])
                    userData = scan_user_scim2_data('groups',userDetails)
                    doNotDisplay = userData[1]
                    userData = userData[0]
                except Exception as e:
                    log('scim2 user data issue for {}: {}'.format(item,e))
                    doNotDisplay = True
                    userData = objData['id']
                    
            elif item == 'host_id':
                    try:
                        #Translate Host_ID value to readable user info
                        userDetails = get_user_scim2_data(objData[item])
                        objData[item] = scan_user_scim2_data('groups',userDetails)
                        try:
                            doNotDisplay = objData[item][1]
                        except:
                            doNotDisplay = True
                        try:    
                            objData[item] = objData[item][0]
                        except:
                            None
                            
                    except Exception as e:
                        log('No scim2 User data found for {}: {}'.format(item,e))
        
        
        for item in objData:
            if not item in jsonKeyIgnore:
                if item == 'first_name' and doNotDisplay == True:
                    None
                    #objData[item] = 'PII Restricted'
                elif item == 'last_name' and doNotDisplay == True:
                    None
                    #objData[item] = 'PII Restricted'
                elif item == 'email' and doNotDisplay == True:
                    objData[item] = 'PII Restricted'
                elif item == 'start_time' or item == 'end_time':
                    # Convert to local timezone from UTC
                    try:
                        itemDateTime = datetime.strptime(objData[item], '%Y-%m-%dT%H:%M:%S%z')
                        setTZ = tz.gettz(location)
                        #localDateTime = pytz.utc.localize(itemDateTime is_dst=None).astimezone(location)
                        #localDateTime = timezone(location).localize(itemDateTime)
                        localDateTime = itemDateTime.astimezone(timezone(location))
                        
                        objData[item] = localDateTime.strftime(date_format)
                        
                    except Exception as e:
                        print("Error in converting date time to PDT: {}: {}".format(objData[item], e))
                elif item == 'duration':
                    objData[item]="{}min".format(objData[item])
                elif item == 'type' and evDesc != "":
                    try:
                        eventType=eventDesc[evDesc]['type']
                        typeNum=str(int(objData[item]))
                        #objData[item]="{}{}".format(userData,eventTypes[eventType][typeNum])
                        if userData != objData['id']:
                                objData[item]="{}".format(userData)
                                
                    except Exception as e:
                        log('Error in scanning meeting types: {}'.format(e))
                elif type(objData[item]) in [list, tuple]:
                    subitemtxt=""
                    for subitems in objData[item]:
                        subitemtxt="{} {}".format(subitemtxt, subitems)
                    objData[item]=subitemtxt
                try:
                    data="{}*{}*: {}\n".format(data, item, objData[item])
                except Exception as e:
                    log("Error in storing data for Tx: {}".format(e))
    except Exception as e:
        log("Error in scanning payload: {}".format(e))

    if objDiff != None:
        data=data + "\n" + "{}".format(objDiff)
        
    if tokenError == True:
        errorMsg = "\n:coin-ce: Zoom account data cannot be retrieved: (JWT Token issue)\n"
        data = "{}\n{}".format(errorMsg,data)

    try:
        if (DEBUG_MODE.lower() == DBG_TRUE):
            requestData=\
            {\
                "text": "```{}```:{}".format(errorLog, slackMsgHeader),\
                "attachments": [{"text": "{}".format(data)}]\
            }
        else:
            requestData=\
            {\
                "text": "{}".format(slackMsgHeader),\
                "attachments": [{"text": data}]\
            }

        print("Request Data to be Tx:{}".format(requestData))

        if DEBUG_MODE.lower() != DBG_DISABLE:
            r = requests.post(url = slackWebhookURI, json = requestData)
            pastebin_url = r.text
            print("{} POST Response is:{}".format(slackWebhookURI, pastebin_url))
    except Exception as e:
        log("Error in request to Slack: {}".format(e))


    log("")
    objData=""
    slackMsgHeader=""



def lambda_handler(event, context):
    '''
        Description:  Processes data coming into AWS Lambda, this
        could be from an AWS API Gateway or AWS SQS that contains
        the webhook event sent from Zoom
    '''
    global slackHeader
    global slackWebhookURI
    global token
    global DEBUG_MODE
    global date
    global setTZ
    global JWT_TOKEN
    global groups
    global location


    # Logging for Cloudwatch
    DEBUG_MODE=os.environ['debugMode']
    token=os.environ['bearerToken']
    JWT_TOKEN=os.environ['JWTToken']
    slackWebhookURI=slackHeader['path']=os.environ['slackHookPath']
    #slackWebhookURI ="https://" + slackHeader['hostname'] + slackHeader['path']
    
    location=os.environ['timezone']
    setTZ=tz.gettz(location)
    date=datetime.now(setTZ)
    
    print("###Raw Event Data: {},\n####Context: {}".format(event, context))
    
    valid=validate_event(event, token)

    if valid == True:
        if 'incident_url' in event:
            statuspage_webhandler(event)
        else:
            groups=get_group_data()
            zoom_webhandler(event)
        
        return {
            'statusCode': 200,
            'body': 'Acknowledge Receipt of Event'
        }
    else:
        return {
            'statusCode': 401,
            'body': 'Not Authorized'
            
        }