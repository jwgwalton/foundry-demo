# Overview
How to setup hosted agents for Microsoft Foundry

## Reference
https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/author-azure-yaml


## Process
azd ai agent init --deploy-mode container 

Follow the steps in the CLI commands linking to existing resources

### Add Toolbox & Connections

Use [https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/use-microsoft-foundry-skill?tabs=vscode as a v](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/author-azure-yaml) This gives an example setup and explains each of the sections.

## Run the Agent

```python
azd ai agent run
```
This runs it locally using the azure.yaml file for setup & also opens a UI for interracting with the Agent at http://127.0.0.1:8087/