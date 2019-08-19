#!/usr/bin/env python3

import datetime
import logging
import os
import sys

import requests
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from statuspage import StatusPageConnection

__author__ = "Ravish Ranjan"

required_env_vars = ["api_key", "jwt", "page_id", "sesam_node_url", "status_page_groups",
                     "min_hours_execution", "max_hours_execution"]


class AppConfig(object):
    pass


config = AppConfig()

# load variables
missing_env_vars = list()
for env_var in required_env_vars:
    value = os.getenv(env_var)
    if not value:
        missing_env_vars.append(env_var)
    setattr(config, env_var, value)

# logging settings
log_level = logging.getLevelName(os.environ.get('LOG_LEVEL', 'DEBUG'))  # default log level = INFO
logging.basicConfig(level=log_level)

logging.debug(datetime.datetime.now())
logging.info(f"SESAM instance name {config.sesam_node_url}")

status_page_conn = StatusPageConnection(config.api_key, config.page_id)

# Global variable
node_all_pipes = list()


def prepare_payload():
    pipe_list = filter_pipes_for_status_page()
    component_group_list = status_page_conn.get_status_page_component_group_list()
    component_list = status_page_conn.get_status_page_component_list()

    valid_component_groups = [g for g in component_group_list if
                              g['GroupName'] in config.status_page_groups]

    if valid_component_groups:
        if pipe_list:
            for pipe in pipe_list:
                for group in pipe['Pipe_Status_Page_Groups']:
                    if group not in [g['GroupName'] for g in valid_component_groups]:
                        logging.error(f"Nothing will happen for invalid Group "
                                      f"Name: \"{group}\" provided for pipe: \"{pipe['Name']}\"")

            unknown_pipes = unknown_node_pipes_on_status_page()

            for valid_group in valid_component_groups:
                # Creation of component  if required:
                create_component(component_list, valid_group, pipe_list)
                # updating component  if required:
                update_component(component_list, valid_group, pipe_list)
                # Deletion of components if required :
                delete_component(component_list, valid_group, pipe_list, unknown_pipes)
    else:
        logging.info(f"No Valid Group Name provided in environmental "
                     f"variable \"status_page_groups\" .So, doing nothing.")


def filter_pipes_for_status_page():
    global node_all_pipes
    node_all_pipes = get_sesam_node_pipe_list()
    if node_all_pipes:
        try:
            filter_pipes = list()
            keys = ['Name', 'Status', 'Pipe_Status_Page_Groups']
            for each_pipe in node_all_pipes:
                if each_pipe['config']['original'].get('metadata') is not None and \
                        each_pipe['config']['original']['metadata'].get('statuspage') is not None:
                    pipe_id = each_pipe['_id']
                    status_groups_name = each_pipe['config']['original']['metadata']['statuspage']
                    status = get_pipe_status(pipe_id)
                    # if each_pipe['runtime']['success']:
                    #     status = 'operational'
                    # else:
                    #     status = 'major_outage'
                    filter_pipes.append(dict(zip(keys, [pipe_id, status, status_groups_name])))
            return filter_pipes
        except Exception as e:
            logging.error(f'issue while filtering pipes for status page {e}')
    else:
        return node_all_pipes


def get_pipe_status(pipe_id):
    pipe_status = 'operational'
    try:
        response = requests.get(url=config.sesam_node_url + "/datasets/system:pump:" + pipe_id +
                                "/entities?deleted=false&history=false&reverse=true&uncommitted=false&limit=2",
                                timeout=180,
                                headers={'Authorization': 'bearer ' + config.jwt})


        if response.ok:
            execution_log_entities = response.json()
            if len(execution_log_entities) > 0:
                latest_log = execution_log_entities[0]  # Pick the most recent execution log entry
                if latest_log['_id'] == 'pump-started':
                    if len(execution_log_entities) > 1:
                        second_latest_log = execution_log_entities[1]  # Pick the second most recent execution log entry
                        if second_latest_log['_id'] == 'pump-failed':
                            pipe_status = 'major_outage'
                        elif second_latest_log['_id'] == 'pump-completed':
                            pipe_status = set_status(latest_log['start_time'],
                                                     datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                    else:
                        pipe_status = set_status(latest_log['start_time'],
                                                 datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                elif latest_log['_id'] == 'pump-completed':
                    pipe_status = set_status(latest_log['start_time'], latest_log['end_time'])
                elif latest_log['_id'] == 'pump-failed':
                    pipe_status = 'major_outage'
            return pipe_status
        else:
            logging.error(f"Issue while fetching node-pipes, got error {response.status_code}")
            pipe_status = 'major_outage'
            return pipe_status
    except Timeout as e:
        logging.error(f"Timeout issue while fetching execution log for pipe: {pipe_id}, got Error : {e}")
        pipe_status = 'degraded_performance'
        return pipe_status
    except ConnectionError as e:
        logging.error(f"ConnectionError issue while fetching execution log for pipe: {pipe_id}, got Error : {e}")
        pipe_status = 'major_outage'
        return pipe_status
    except Exception as e:
        logging.error(f"issue while fetching execution log for pipe: {pipe_id}, got Error : {e}")
        pipe_status = 'major_outage'
        return pipe_status


def set_status(start_time, end_time):
    diff = datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S.%fZ') - \
           datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S.%fZ')
    hours = diff.total_seconds() / 3600
    if hours <= float(config.min_hours_execution):
        return 'operational'
    elif float(config.min_hours_execution) < hours <= float(config.max_hours_execution):
        return 'partial_outage'
    else:
        return 'major_outage'


def get_sesam_node_pipe_list():
    try:
        response = requests.get(url=config.sesam_node_url + "/pipes", timeout=180,
                                headers={'Authorization': 'bearer ' + config.jwt})
        if response.ok:
            return response.json()
        else:
            logging.error(f"Issue while fetching node-pipes, got error {response.status_code}")
            sys.exit(1)
    except Timeout as e:
        logging.error(f"Timeout issue while fetching node pipes {e}")
        update_all_component_directly("degraded_performance")
    except ConnectionError as e:
        logging.error(f"ConnectionError issue while fetching node pipes {e}")
        update_all_component_directly("major_outage")
    except Exception as e:
        logging.error(f"issue while fetching node pipes {e}")
        sys.exit(1)


def update_all_component_directly(status):
    component_group_list = status_page_conn.get_status_page_component_group_list()
    component_list = status_page_conn.get_status_page_component_list()

    valid_component_groups = [g for g in component_group_list if
                              g['GroupName'] in config.status_page_groups]

    if valid_component_groups:
        # updating the component with based on error message:
        for valid_group in valid_component_groups:
            update_payload_list = [d for d in component_list if d['GroupId'] == valid_group['GroupId']]
            if update_payload_list:
                for update_item in update_payload_list:
                    update_item['Status'] = status
                    update_item.update({'GroupName': valid_group['GroupName']})
                    status_page_conn.update_component_status_page(update_item)

    else:
        logging.info(f"No Valid Group Name provided in environmental "
                     f"variable \"status_page_groups\" .So, doing nothing.")


def unknown_node_pipes_on_status_page():
    try:
        unknown_pipe_list = list()
        keys = ['Name']
        for each_pipe in node_all_pipes:  # use the global variable & save one call to SESAM api.
            if each_pipe['config']['original'].get('metadata') is None or (
                    each_pipe['config']['original'].get('metadata') is not None and
                    each_pipe['config']['original']['metadata'].get('statuspage') is None):
                pipe_id = each_pipe['_id']
                unknown_pipe_list.append(dict(zip(keys, [pipe_id])))
        return unknown_pipe_list
    except Exception as e:
        logging.error(f"issue while filtering pipes inside method unknown_pipes_of_statuspage {e}")



def create_component(component_list, valid_group, pipe_list):
    create_payload_list = [d for d in pipe_list if d['Name'] not in [p['Name'] for p in component_list
                                                                     if p['GroupId'] == valid_group['GroupId']] and
                           valid_group['GroupName'] in d['Pipe_Status_Page_Groups']]
    if create_payload_list:
        for create_item in create_payload_list:
            create_payload = dict()
            create_payload['Name'] = create_item['Name']
            create_payload['Group_Id'] = valid_group['GroupId']
            create_payload['Status'] = create_item['Status']
            create_payload['GroupName'] = valid_group['GroupName']
            status_page_conn.create_component_status_page(create_payload)


def update_component(component_list, valid_group, pipe_list):
    update_payload_list = [d for d in component_list for x in pipe_list if d['Name'] == x['Name'] and
                           d['Status'] != x['Status'] and valid_group['GroupName'] in x['Pipe_Status_Page_Groups']
                           and d['GroupId'] == valid_group['GroupId']]

    if update_payload_list:
        for update_item in update_payload_list:
            d = next(item for item in pipe_list if item['Name'] == update_item['Name'])
        update_item['Status'] = d['Status']
        update_item.update({'GroupName': valid_group['GroupName']})
        status_page_conn.update_component_status_page(update_item)


def delete_component(component_list, valid_group, pipe_list, unknown_pipes):
    delete_payload_list = [d for d in component_list for x in pipe_list if d['Name'] == x['Name'] and
                           d['GroupId'] == valid_group['GroupId'] and d['Status'] != 'major_outage' and
                           valid_group['GroupName'] not in x['Pipe_Status_Page_Groups']]

    if delete_payload_list:
        for delete_item in delete_payload_list:
            # Adding a new key value pair to just log Group Name
            delete_item['Status'] = "major_outage"
            delete_item.update({'GroupName': valid_group['GroupName']})
            # No hard delete only change the status and Admin of status page will decide to keep it or not.
            status_page_conn.update_component_status_page(delete_item)

    # delete un-wanted or unknown components if any from status-page (clean-up task)
    unknown_delete_payload_list = [d for d in component_list for x in unknown_pipes
                                   if d['Name'] == x['Name'] and d['Status'] != 'major_outage'
                                   and d['GroupId'] == valid_group['GroupId']]

    if unknown_delete_payload_list:
        for unknown_delete_item in unknown_delete_payload_list:
            unknown_delete_item['Status'] = "major_outage"
            unknown_delete_item.update({'GroupName': valid_group['GroupName']})
            # No hard delete only change the status.
            status_page_conn.update_component_status_page(unknown_delete_item)


if __name__ == '__main__':
    if len(missing_env_vars) != 0:
        logging.error(f"Missing the following required environment variable(s) {missing_env_vars}")
        sys.exit(1)
    else:
        prepare_payload()
