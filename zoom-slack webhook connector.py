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
import copy
import sys
import linecache
import csv

from datetime import datetime
from dateutil import tz


##@@@@TODO
#prep for SQS usage
#Plan is to retrieve and delete items from queue
# While API Gateways sends data to queue
import boto3  


##GLOBAL VARIABLES
DBG_DISABLE = "disable"
DBG_TRUE = "true"
DBG_FALSE = "false"
DEBUG_MODE = DBG_DISABLE
date_format = '%m/%d/%Y %H:%M:%S %Z'
date_format_12h = "%m/%d/%Y %I:%M:%S %p %Z"
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
        "user.settings_updated":
        {
            "name": "User Settings Updated",
            "emoji": ":ballot_box_with_check:",
            "type": "user"
        },
        "user.updated":
        {
            "name": "User Profile Updated",
            "emoji": ":ballot_box_with_check:",
            "type": "user"
        },        
         "user.deleted":
        {
            "name": "User Deleted",
            "emoji": ":x:",
            "type": "license"
        },
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
        "user.invitation_accepted":
        {
            "name":"User Invitation Accepted",
            "emoji":":email:",
            "type":"license"
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
        'rolesList':'https://api.zoom.us/v2/roles/@/members',
        'subaccount':'https://api.zoom.us/v2/accounts'
    }


def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    log (f"++Exception in ({filename}, LINE {lineno}, {line.strip()}: {exc_obj}")

def readFromS3(objName, init = {},  bucket = 'lambda-custom-s3'):
    
    dataDict = init
    
    try:
        s3 = boto3.resource('s3')
        content_object = s3.Object(bucket, objName)
        file_content = content_object.get()['Body'].read().decode('utf-8')
        dataDict = json.loads((file_content))
        log(f"S3 Object Data: {dataDict}")
    except Exception as e:
        log (f"!S3 Object read error: {e}")    
    
    return dataDict
    
    
def writeToS3(objName, bucket = 'lambda-custom-s3'):
    try:    
        s3_client = boto3.client('s3')
        response = s3_client.upload_file(objName, 'lambda-custom-s3', objName)
    except Exception as e:
        template = "An error uploading file to S3 Bucket: exception of type {0} occurred. Arguments:\n{1!r}"
        message = template.format(type(e).__name__, e.args)
  
def writeCSVdata():
    log("Retrieving data in S3 Bucket for function:  writeCSVdata")
    dataTracking = retrieve_data()
    
    os.chdir('/tmp')
    
    dateFormat = "%d-%m-%Y"
    
    try:
        fileName = "License Tracking.csv"
        with open(fileName, 'w', newline='') as outcsv:
            writer = csv.DictWriter(outcsv, fieldnames = ["Date", "Licenses", "Remaining", "Pro Licenses Added", "Pro Licenses Deleted","Basic Licenses Added","Basic Licenses Deleted"])
            writer.writeheader()
            
            for timestamp in dataTracking:
                try:
                    data = dataTracking[timestamp]['licenses']
                    writer.writerow({\
                        "Date": timestamp, 
                        "Licenses": data["total"],
                        "Remaining":data["remaining"],
                        "Pro Licenses Added":data['Licensed']['added'],
                        "Pro Licenses Deleted":data['Licensed']['deleted'],
                        "Basic Licenses Added":data['Basic']['added'],
                        "Basic Licenses Deleted":data['Basic']['deleted']
                        })
                except KeyError as e:
                    None
        writeToS3(fileName)            
    except Exception as e:
        PrintException()
        log(f"CSV Write Error: {e}")
    try:
        fileName = "User Setting Tracking.csv"
        with open(fileName, 'w', newline='') as outcsv:
            writer = csv.DictWriter(outcsv, fieldnames = ["Date", "Group", "Category", "Setting","Value","Count"])
            writer.writeheader() 
            
            for timestamp in dataTracking:
                try:
                    test = time.strptime(timestamp, "%d-%m-%Y")   
                    try:
                        data = dataTracking[timestamp]['updates']
                        #print(f'##Found Timestamp to record in CSV: {timestamp}')
                    except:
                        data = {}
                except Exception as e:
                    #print (f"Error in timstamp value in json file:{e}")
                    data = {}
                
                    
                try:
                    if data != {}:
                        for group in data:
                            #print(f'##Found Group to record in CSV: {group}')
                            try:
                                for category in data[group]:
                                    #print(f"Find category: {category}")
                                    try:
                                        for setting in data[group][category]:
                                            #print(f"Find setting: {setting}")
                                            try:
                                                for flag in data[group][category][setting]:
                                                    csvRow = {\
                                                        "Date": timestamp,
                                                        "Group": group,
                                                        "Category":category,
                                                        "Setting":setting,
                                                        "Value":flag,
                                                        "Count":data[group][category][setting][flag]
                                                        }
                                                    writer.writerow(csvRow)  
                                                    #print(f"CSV Row: {csvRow}")
                                            except Exception as e:
                                                #print('Error in CSV flag data: {e}')
                                                None
                                    except:
                                            #PrintException()
                                            None
                                            
                            except:
                                #print("Issue in building categories:")
                                #PrintException()
                                None
                    
                except:
                    #print("Issue in building groups:")
                    #PrintException()
                    None
        writeToS3(fileName)
    except:
        PrintException()
        
    
        
def store_data(dictData):
    os.chdir('/tmp')
    temp = copy.deepcopy(dictData)
    
    ## Item, Date, value
    ## Date:  datetime.datetime.now().date()
    

    
    try:
        with open('data.json', 'w') as jsonFile:
           json.dump(temp, jsonFile, sort_keys=True, ensure_ascii=False, indent=2)
    except Exception as e:
        print (f"Error Saving File: {e}")

    writeToS3('data.json')
    


def retrieve_data():
    def check_data(data):
        timestamp = timeGet()
        
        try:
            if not timestamp in data:
                data[timestamp] = {}
                store_data(data)
                writeCSVdata()
            
            if not "licenses" in data[timestamp]:
                data[timestamp]["licenses"] = {}
            
            if not "updates" in data[timestamp]:
                data[timestamp]["updates"] = {}        
            
            desc = "licenses"
            
            if not "Basic" in data[timestamp]["licenses"]:
                licType = "Basic"
                data[timestamp][desc][licType] = {}
                data[timestamp][desc][licType]["added"] = 0
                data[timestamp][desc][licType]["deleted"] = 0
        
            if not "Licensed" in data[timestamp]["licenses"]:
                licType = "Licensed"
                data[timestamp][desc][licType] = {}
                data[timestamp][desc][licType]["added"] = 0
                data[timestamp][desc][licType]["deleted"] = 0
        except Exception as e:
            log(f"!Error in generating JSON data structure: {e}")
        
        return data        
    
    os.chdir('/tmp')
    
    dataDict =\
        {
            "Start":{}
        }    
    
    
    dataDict = readFromS3('data.json', init = dataDict)
              
    contents = check_data(dataDict)
    
    return contents


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
        log(f"Error validating event: {e}")

    return state

def duplicate_event(msg):
    ''' Description:  This function validates the authorization token in the 
        message, not the JWT/OAuth token
    '''
    state = False

    try:
        retryCount = msg['headers']['x-zoom-retry-num']
        if int(retryCount) > 0:
            reason = msg['headers']['x-zoom-retry-reason']
            state = True
            log(f'Duplicate Event #{retryCount} Ignored:  {reason}')
    except Exception as e:
        return state
        
    return state    

def send_REST_request(apiType, data=""):
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
            log(f'Error in url replace: {e}')

        api = f"{url}"

        accessToken = 'Bearer ' + JWT_TOKEN
        authHeader = {'Authorization': accessToken}
        log(f"Sending HTTP REST request for: {api}")
       
        start = time.time()
        try:
            response = requests.get(url=api, headers=authHeader)
        except Exception as e:
            log(f'Send HTTP REST Request {api}, Response: {response}, Error:{e}')     
        try:       
            roundtrip = time.time() - start
            status = response.status_code
            respTime = response.elapsed
            respData = response.json()
            log('HTTP REST {} Request Response Processing Time:{} Roundtrip Time:{}, Request Response: {},\n**RAW Request DATA: {}'.format(\
                apiType,respTime, roundtrip, response, respData))
            
            if status == 404:
                try:
                    return respData['detail']
                except:
                    return "Error"
            elif status != 200 or 'code' in respData:
                log('Send JWT Token error: Code:{} Message:{}'.format(respData['code'],respData['message']))
                return "\n:coin-ce: Zoom account data cannot be retrieved: (JWT) {}\n".format(respData['message'])
            else:
                tokenError = False
        except Exception as e:
            PrintException()
            log('Processing HTTP REST Request {} error:{}'.format(api, e))
        
    return respData


def get_acct_info(acctID):

    rolesData = ""
    
    #acctInfo = send_REST_request('account', acctID)
    #@ToDo further automation by searching list and roles
    
    rolesInfo = send_REST_request('rolesList','0')
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

def get_subaccount_data():
    try:
        subAccount = send_REST_request('subaccount', data='')
    except Exception as e:
        log("Error getting sub account data: {}".format(e))
        subAccount = None
    
    try:
        seats = 0
        for data in subAccount['accounts']:
            if 'seats' in data:
                seats += data['seats']
    except:
        seats = 0
        
    
    return (subAccount,seats)
        
def get_group_data():
    total_records = None
    response = None
    groupData = {}
    groups = ""

    try:
        groups = send_REST_request('groups', data='')
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

def get_user_scim2_group(scim2data,index = 1):
    group = 'No Zoom Group'
    cnt = 0
    if 'groups' in scim2data:
        if scim2data['groups'] == []:
                group = "No Zoom Group"
        else:
            for gItem in scim2data['groups']:
                group = f"{gItem['display']}"
                cnt += 1
                if cnt >= index:
                    break
    return group    
    
def get_user_scim2_data(userID):
    # log('Checking SCIM2 Data for {}'.format(userID))
    # urn = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
    userInfo = ''

    try:
        userInfo = send_REST_request('scim2', userID)
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
            userString = f"{userName}, {data}, {userType} account "   
        else:
            userString = f"{data}, {userType} account "
            
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
            
        if 'userName' in scim2data and doNotDisplay == True:
            scim2data['userName'] = 'PII Restricted Info'
    
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
                    group = 'Group:  {} {}'.format(gItem['display'], group)
                    group = group.rstrip()
                    if pii_check(gItem['display'],scim2data) == True:
                        break
            userInfo = userInfoString(group, scim2data)
    else:
        group = noAssigned
        userInfo = userInfoString(group, scim2data)
    log (f"User Info: {[userInfo,doNotDisplay, scim2data['userType']]}")
    return [userInfo,doNotDisplay, scim2data['userType']]

def getLicenseInfo(desc):
    planInfo = send_REST_request('plan', 'me')
    (subAccount, seats) = get_subaccount_data()

    
    try:
        planLicenses = planInfo["plan_base"]["hosts"] + seats
        planUsers = planInfo["plan_base"]["usage"]
        remainingNow = planLicenses - planUsers
        remainingPct = round(((remainingNow / planLicenses) * 100),2)
        
        returnStr =  f"\nRemaining licenses:  {remainingPct}%, {remainingNow} (out of {planLicenses})"
        #@@TODO
        try:
            dataStr = tracking('licenses',remainingNow,planLicenses,planUsers)
        except Exception as e:
            log(f"Error in tracking dataStr: {e}")
            dataStr = [0,0]
            
        #returnStr = f"{returnStr}Licenses {desc} today:  {dataStr[0]}\n"
        
        if dataStr[1] != 0:
            returnStr = f"{returnStr}\nTotal Available Licenses changed:  {dataStr[1]}\n"
            
        return returnStr
    except Exception as e:
        print ("Exception in License info: {}".format(e))
        return planInfo
    
    return ""
    
    
def eventProcessing(name, accountID):
    '''
        Description:  does transformation/calculations of specific data
                      based on zoom accountID
          Parameters: name - string to identify event being processed to pull
                      appropriate account information to be processed
                      accountID - Zoom accountID provided in webhook payload
             Return:   Returns value 
    '''

    # if user created, check # of licenses in use and validate remaining licenses
    log('Event Processing: {} {}'.format(name, accountID))
    
    returnStr = ""
    
    if name == "User Created":
        returnStr = getLicenseInfo("added")
    elif name == "User Deleted":
        returnStr = getLicenseInfo("deleted")
            
    return returnStr
        

def dailyLicenseUsage(licType,timestamp, delta):
    
    desc = "licenses"
    
    log("Retrieving data in S3 Bucket for function:  dailyLicenseUsage")
    dataTracking = retrieve_data()
    licenseCnt = 0
    try:
        #Manual tracking of license vs calculating with total number of licenses
        # is a little more accurate except for the fact test data will increment
        # this number
        # will also need to track license removals to keep this accurate.
        # Basic Licenses have to be manually tracked since the API currently
        # does not have provide a total count with out querying and summing
        # each user's license status
        try:
            usedPrevious = dataTracking[timestamp][desc]["usedPrevious"]
        except:
            dataTracking[timestamp][desc]["usedPrevious"] = -1  
            usedPrevious = dataTracking[timestamp][desc]["usedPrevious"]
            
        try:    
            used = dataTracking[timestamp][desc]["used"]
        except:
            dataTracking[timestamp][desc]["used"] = 0
            used = dataTracking[timestamp][desc]["used"]
        
        licenseDiff = used - usedPrevious
        
        log (f"Used Previous Licenses:  {usedPrevious}, current {used}, Diff: {licenseDiff}, Current User: {licType}")
        
        usedPrevious = used
        
        if delta > 0:
            if licenseDiff < 0 or licType.lower() == "basic" :
                dataTracking[timestamp][desc][licType]["added"] += 1
            elif licenseDiff > 0:
                dataTracking[timestamp][desc][licType]["added"] += licenseDiff
            else:
                print ("No change in license quantity")
            
            licenseCnt =  dataTracking[timestamp][desc][licType]["added"]
            print(f"Daily Licenses Added: {licenseCnt}")
        else:
            if licenseDiff > 0 or licType.lower() == "basic" :
                dataTracking[timestamp][desc][licType]["deleted"] += 1
            elif licenseDiff < 0:
                dataTracking[timestamp][desc][licType]["deleted"] += licenseDiff
            
            licenseCnt = dataTracking[timestamp][desc][licType]["deleted"]
    except Exception as e:
        PrintException()
        log(f"Error in dailyLicenseUsage tracking {timestamp} {desc} {licType}: {e}")
    
    store_data(dataTracking)    
    
    return licenseCnt          
  
    
def tracking(desc,*args):
    log("Retrieving data in S3 Bucket for function:  tracking")
    dataTracking = retrieve_data()
    
    dataStr = ""
    totalPrev = 0
    timestamp = timeGet()
        
    try:
        if desc == "updates":
            (group,category,setting,flag) = args
            
            flag = f"{flag}"
            
            try:
                if not group in dataTracking[timestamp][desc]:
                    dataTracking[timestamp][desc][group] = {}
                
                if not category in dataTracking[timestamp][desc][group]:
                     dataTracking[timestamp][desc][group][category] = {}
                     
                if not setting in dataTracking[timestamp][desc][group][category]:
                     dataTracking[timestamp][desc][group][category][setting] = {}
                     
                if not flag in dataTracking[timestamp][desc][group][category][setting]:
                    dataTracking[timestamp][desc][group][category][setting][flag]=0
                    
                dataTracking[timestamp][desc][group][category][setting][flag] += 1 
                    
                dataStr = dataTracking[timestamp][desc][group][category][setting][flag]
            except Exception as e:
                log(f"Error in user update tracking: {e}")    
          
        if desc == "licenses":
            (remainingNow,totalLicenses,usedLicenses) = args
            
            if not "remaining" in dataTracking[timestamp][desc]:
                dataTracking[timestamp][desc]["remaining"] = remainingNow
                dataTracking[timestamp][desc]["remainingPrevious"] = copy.copy(remainingNow)
                dataTracking[timestamp][desc]["total"] = totalLicenses
                dataTracking[timestamp][desc]["totalPrevious"] = copy.copy(totalLicenses)
                dataTracking[timestamp][desc]["used"] = copy.copy(usedLicenses) -1
                dataTracking[timestamp][desc]["usedPrevious"] = 0
                totalPrev = totalLicenses
    
    
            try:
                remainingPrev = dataTracking[timestamp][desc]["remaining"]
                dataTracking[timestamp][desc]["remainingPrevious"] = copy.copy(remainingPrev)
                dataTracking[timestamp][desc]["totalPrevious"] = copy.copy(dataTracking[timestamp][desc]["total"])
                dataTracking[timestamp][desc]["usedPrevious"] =  copy.copy(dataTracking[timestamp][desc]["used"])
                dataTracking[timestamp][desc]["used"] = copy.copy(usedLicenses)
                totalPrev = dataTracking[timestamp][desc]["totalPrevious"]
            except Exception as e:
                PrintException()
                print (f"Error in remainingPrev: {e}")

            
            dataTracking[timestamp][desc]["remaining"] = remainingNow
            dataTracking[timestamp][desc]["total"] = totalLicenses
            
            dataStr = [remainingNow-remainingPrev,totalLicenses-totalPrev]
        
    except Exception as e:
        log("Error in tracking data: {}".format(e))

    
    #SAVE FILE in tmp
    store_data(dataTracking)
    
    
    return dataStr
    
def timeGet():
    try:
        ##@@ Timezone compensation may be needed by reading incoming JSON data timezone
        location=os.environ['timezone']
        setTZ=tz.gettz(location)
        date=datetime.now(setTZ)
        timeStr = date.strftime("%d-%m-%Y")        
    except Exception as e:
        log(f"Time formatting error:  {e}")
        timeStr = datetime.now()
    
    return timeStr
    
    
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
    licenses = ""

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
    eventTxt = ""
    eventEmoji = ""
    eventData = ""
    try:
        global eventDesc
        slackMsgTitle = "\n" + "*_" + ":exclamation:" + \
            "Notice" + "_*" + ":\n" + date.strftime(date_format_12h)

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
                    slackMsgTitle =  f"*_{eventEmoji}{eventTxt}_*"
                    eventData = eventProcessing(eventTxt, zoomAccount)
                    slackMsgHeader = "\n" + \
                        date.strftime(date_format_12h) + \
                        "{}".format(eventData)
            except Exception as e:
                log("Error in event description {}: {}".format(evDesc, e))
                slackMsgHeader = "{}\n{}".format(
                    slackMsgHeader, objBody['event'])

    except Exception as e:
        log('Notice: No event in message: {}'.format(e))

    objPayload = {}
    try:
        slackMsgGroup = ""
        objPayload = objBody['payload']
        # log("objPayload {}: {}".format(type(objPayload),objPayload))
        if 'operator_id' in objPayload:
            userID = objPayload['operator_id']
            scim2data = get_user_scim2_data(userID)
            userGroup = get_user_scim2_group(scim2data)
            slackMsgGroup = f", {userGroup}"
            
        if 'operator' in objPayload:
            extraData = ""
            if objPayload['operator'] == owner:
                objPayload['operator'] = 'Account Owner'
            if 'creation_type' in objPayload:
                extraData = " ({})".format(objPayload['creation_type'])
                slackMsgGroup = ""
            slackMsgHeader = f"Updated By:  {objPayload['operator']}{slackMsgGroup}{extraData}{slackMsgHeader}"
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
    except:
        #No old_object
        objDataOld = None
        
    try:
        if  objDataOld != None:
            # log("old_object Type:{}".format(type(objDataOld)))
            # objDiff = { d : objDataOld[d] for d in set(objDataOld) - set(objData) }
            objDiff = ""
            for key1 in objDataOld['settings']:
                for key2 in objDataOld['settings'][key1]:
                    if objDataOld['settings'][key1][key2] != objData['settings'][key1][key2]:
                        objDiff = "{}".format(objDataOld['settings'][key1][key2])
                        objdiffcnt = tracking("updates",userGroup,key1,key2,objData['settings'][key1][key2])
                        break
                    else:
                        objDiff = "A change has been made to the account, but the change is currently not documented in Zoom's API"
    except Exception as e:
        log("API Issue:  Error with old_object data: {}".format(e))
        objDataOld = {}
        objDiff = None

    try:
        doNotDisplay = False
        data = ""
        userData = ""
        
        #Scan for user IDs first to identify PII classification level
        for item in objData:
            
            if item == 'id' and eventTxt == "User Deleted":
                    doNotDisplay = False
                    userData = f'{objData["email"]} does not exist '
            elif item == 'id' and (eventTxt == "User Created" or eventTxt == "User Invitation Accepted"):
                try:
                    # Lookup ID to crossreference group membership
                    userDetails = get_user_scim2_data(objData[item])
                    userData = scan_user_scim2_data('groups',userDetails)
                except Exception as e:
                    log(f'{eventTxt}:  SCIM2 user data issue for {item}: {e}')
                    doNotDisplay = True
                    userData = objData['id']
                try:
                    doNotDisplay = userData[1]
                    licenses = dailyLicenseUsage(userData[2],timeGet(),1)
                    slackMsgHeader = f"{slackMsgHeader}\n{userData[2]} users added today: {licenses}"
                    userData = userData[0]
                except Exception as e:
                    log(f'{eventTxt}: user license data issue for {item}: {e}')
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
                        log(f'No scim2 User data found for {item}: {e}')
        
        
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
                        ## @@TODO - Fix timezone correction
                        itemDateTime = datetime.strptime(objData[item], '%Y-%m-%dT%H:%M:%S%z')
                        setTZ = tz.gettz(location)
                        #localDateTime = pytz.utc.localize(itemDateTime is_dst=None).astimezone(location)
                        #localDateTime = timezone(location).localize(itemDateTime)
                        localDateTime = itemDateTime.astimezone(timezone(location))
                        
                        objData[item] = localDateTime.strftime(date_format_12h)
                        
                    except Exception as e:
                        print(f"Error in converting date time to PDT: {objData[item]}: {e}")
                elif item == 'duration':
                    objData[item]=f"{objData[item]}min"
                elif item == 'type' and evDesc != "":
                    try:
                        eventType=eventDesc[evDesc]['type']
                        if userData != objData['id']:
                            try:
                                typeNum=int(objData[item])
                               
                                typeStr = str(typeNum)
                                if eventTxt == "User Deleted":
                                    objData[item] = eventTypes[eventType][typeStr]
                                    licenses = dailyLicenseUsage(objData[item],timeGet(), -1)
                                    slackMsgHeader = f"{slackMsgHeader}\n{objData[item]} users deleted today: {licenses}"
                                   
                                elif eventType == 'license':
                                    objData[item] = f"{userData}"
                                else:
                                    objData[item] = f"{userData}{eventTypes[eventType][typeStr]}"
                            except Exception as e:
                                None
                            
                        #print("@@@@User Data: {}\n@@@objData: {}".format(userData,objData[item]))        
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
                    log(f"Error in storing data for Tx: {e}")
    except Exception as e:
        PrintException()
        log(f"Error in scanning payload: {e}")

    if objDiff != None:
        data= f"{data}\n*Previous Settings:*\n{objDiff}"
        
    if tokenError == True:
        #errorMsg = "\n:coin-ce: Zoom account data cannot be retrieved: (JWT Token issue)\n"
        #data = "{}\n{}".format(errorMsg,data)
        None
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
                "text": f"{slackMsgTitle}\n{slackMsgHeader}",\
                "attachments": [{"text": data}]\
            }

        print(f"Request Data to be Tx:{requestData}")

        if DEBUG_MODE.lower() != DBG_DISABLE:
            r = requests.post(url = slackWebhookURI, json = requestData)
            pastebin_url = r.text
            print(f"{slackWebhookURI} POST Response is:{pastebin_url}")
    except Exception as e:
        PrintException()
        log(f"Error in request to Slack: {e}")


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
    print("##### NEW EVENT #####")
    print(f"###Raw Event Data: {event},\n####Context: {context}")
    
    valid=validate_event(event, token)
    
    deduplication = duplicate_event(event)
    
    
    if valid == True and deduplication == False:
        if 'incident_url' in event:
            statuspage_webhandler(event)
        else:
            groups=get_group_data()
            zoom_webhandler(event)
            writeCSVdata()
        
        return {
            'statusCode': 200,
            'body': 'Acknowledge Receipt of Event'
        }
    else:
        return {
            'statusCode': 401,
            'body': 'Error'
            
        }