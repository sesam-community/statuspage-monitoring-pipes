import json
import logging
import time

import requests

logger = logging.getLogger('Status_page_Manager')


class StatusPageConnection(object):
    BASE_URL = 'https://api.statuspage.io/v1'

    def __init__(self, api_key, page_id):
        self.api_key = api_key,
        self.page_id = page_id

        headers = {
            'Authorization': api_key
        }
        self.session = session = requests.Session()
        session.headers = headers

    def create_component_status_page(self, item):
        try:
            if item:
                data_send = {'component': {'name': item['Name'], 'group_id': item['Group_Id'], 'status': item['Status'],
                                           'only_show_if_degraded': False, 'showcase': True}}
                json_data = json.dumps(data_send)
                url = self.BASE_URL + '/pages/' + self.page_id + '/components/'
                response = self.session.post(url, data=json_data)
                if response.ok:
                    logging.info(f"Component \"{item['Name']}\" added successfully for "
                                 f"Group: \"{item['GroupName']}\" on status-page.")
                time.sleep(1)
        except Exception as e:
            logging.error(f"Issue while creating components through status page api {e}")

    def update_component_status_page(self, item):
        if item['GroupId'] is not None:
            payload = {'component': {'status': item['Status'], 'group_id': item['GroupId']}}
        else:
            payload = {'component': {'status': item['Status']}}
        json_data = json.dumps(payload)
        try:
            url = self.BASE_URL + f'/pages/' + self.page_id + '/components/' + item['ComponentId']
            response = self.session.patch(url, data=json_data)
            if response.ok:
                logging.info(f"Component \"{item['Name']}\", has been updated successfully for "
                             f"Group: \"{item['GroupName']}\" on status-page.")
            time.sleep(1)
        except Exception as e:
            logging.error(f"Issue while updating components for status page : {e}")

    def delete_component_status_page(self, item):
        try:
            url = self.BASE_URL + '/pages/' + self.page_id + '/components/' + item['ComponentId']
            response = self.session.delete(url)
            time.sleep(1)
            if response.ok:
                logging.info(
                    f"Component \"{item['Name']}\" deleted successfully from "
                    f"Group: \"{item['GroupName']}\" on status-page.")
        except Exception as e:
            logger.error(f"Error while deletion from delete_component_status_page : {e}")

    def get_status_page_component_list(self):
        try:
            url = self.BASE_URL + '/pages/' + self.page_id + '/components/'
            response = self.session.get(url)
            component_list = list()
            if response.ok:
                component_keys = ['Name', 'Status', 'ComponentId', 'GroupId']
                for li in response.json():
                    if li['group'] is False:
                        component_id = li['id']
                        status = li['status']
                        name = li['name']
                        group_id = li['group_id']
                        component_list.append(dict(zip(component_keys, [name, status, component_id, group_id])))
                time.sleep(1)
                return component_list
            else:
                logging.error(f"Issue while fetching components from status-page api got: {response.status_code}")
                return component_list
        except Exception as e:
            logging.error(f"Issue while fetching status-page api while fetching components{e}")

    def get_status_page_component_group_list(self):
        try:
            url = self.BASE_URL + '/pages/' + self.page_id + '/component-groups/'
            response = self.session.get(url)
            component_group_list = list()
            if response.ok:
                component_group_keys = ['GroupName', 'GroupId']
                for li in response.json():
                    component_group_id = li['id']
                    name = li['name']
                    component_group_list.append(dict(zip(component_group_keys, [name, component_group_id])))
                time.sleep(1)
                return component_group_list
            else:
                logging.error(
                    f"Issue while fetching components groups from status-page api, got: {response.status_code}")
                return component_group_list
        except Exception as e:
            logging.error(f"Issue while connecting status-page api while fetching components groups {e}")
