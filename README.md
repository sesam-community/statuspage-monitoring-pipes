### Status-page-Monitoring-Pipes

**`Example of a system-config for this micro-service.`**

```json
{
  "_id": "<Name of the system>",
  "type": "system:microservice",
  "docker": {
    "environment": {
      "LOG_LEVEL": "INFO",
      "api_key": "<api-key of the status page>",
      "jwt": "<token to access node>",
      "page_id": "<page-id>",
      "sesam_node_url": "https://<node-instance>.sesam.cloud/api",
      "status_page_groups": ["<comma separated name of component groups of status page like "Group1", "Group2">"]
    },
    "image": "<docker image of the micro-service>",
    "port": 5000
  },
  "verify_ssl": true
}
```

**`Now, to use this micro-service,you need to add mandatory "metadata" tag in your required pipe configuration that you
want to monitor on status page.Below, is one example of creating one such configuration for pipe "test-notifications".`**


```json
{
  "_id": "<Name of the pipe>",
  "type": "pipe",
  "metadata": {
    "statuspage": ["<comma separated name of component groups of status page like "Group1", "Group2">"]
  }
}

```

    Few things to follow:
        1. "statuspage" is mandatory tag and it is list of valid component groups of status page. 
        2. Please ensure that, component group name should valid (matches with name provided while creating system on 
        node).it is also case-sensative.
        3. Please be informed that if any pipe or component, who had earlier on status page but now removed from 
        pipe-configuration (for that component group)that would be set as status "major_outage" on 
        status-page.
