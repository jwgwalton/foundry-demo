# Overview

* Create a project in Microsoft Foundry
* Update .env with the Project URL shown at creation
* Deploy a Model in Foundry
* Update the deployment name in .env
* Create a service principal so that i can use the default credentials
    * az login (had to use az login --tenant ${TENANT_ID}
    * az ad sp create-for-rbac --name "foundry-local-dev"
        * returns {
                "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "displayName": "foundry-local-dev",
                "password": "xxxxxxxxxxxxxxxx",
                "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                }

    * Assign the appropriate priviledges to the Service Principal
        $SP_APP_ID = "<your-AZURE_CLIENT_ID>": = appId from response
        $RESOURCE_GROUP = "<your-resource-group>": Find from Azure Portal
        $FOUNDRY_RESOURCE = "<your-foundry-resource>": Find from Azure Portal

        $FOUNDRY_RESOURCE_ID = az cognitiveservices account show `
            --name $FOUNDRY_RESOURCE `
            --resource-group $RESOURCE_GROUP `
            --query id `
            --output tsv

        az role assignment create `
            --assignee $SP_APP_ID `
            --role "Foundry User" `
            --scope $FOUNDRY_RESOURCE_ID
            
    * Map to .env
        AZURE_CLIENT_ID=<appId>
        AZURE_TENANT_ID=<tenant>
        AZURE_CLIENT_SECRET=<password>

        FOUNDRY_PROJECT_ENDPOINT=https://...
        AZURE_AI_MODEL_DEPLOYMENT_NAME=...


* docker build . -t foundry_agent      
* docker run --env-file .env -p 8088:8088 foundry_agent    

## Create the toolbox
This needs to only be ran once per change to the file.
```python
uv run create_toolboxes.py
```

* Invoke-RestMethod `
  -Uri "http://localhost:8088/responses" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
      input = "What is the weather in London today?"
  } | ConvertTo-Json)
