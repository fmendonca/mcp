import uvicorn
from fastapi import FastAPI, HTTPException
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os

app = FastAPI(title="Kubernetes/OpenShift MCP Server")

# Load kube config (inside cluster or local)
try:
    config.load_incluster_config()
except config.ConfigException:
    try:
        config.load_kube_config()
    except config.ConfigException:
        raise RuntimeError("Could not configure kubernetes client")

core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
custom_objects = client.CustomObjectsApi()

# Constants
KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
KUBEVIRT_PLURAL = "virtualmachines"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/namespaces")
def list_namespaces():
    try:
        ns = core_v1.list_namespace()
        return [{"name": item.metadata.name, "status": item.status.phase} for item in ns.items]
    except ApiException as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/pods")
def list_pods(namespace: str):
    try:
        pods = core_v1.list_namespaced_pod(namespace)
        return [{"name": p.metadata.name, "phase": p.status.phase} for p in pods.items]
    except ApiException as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/virtualmachines")
def list_virtualmachines(namespace: str):
    try:
        vms = custom_objects.list_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL
        )
        return vms.get("items", [])
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="KubeVirt CRD not found or no VMs")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/namespaces/{namespace}/virtualmachines/{vm_name}")
def get_virtualmachine(namespace: str, vm_name: str):
    try:
        vm = custom_objects.get_namespaced_custom_object(
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural=KUBEVIRT_PLURAL,
            name=vm_name
        )
        return vm
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail="VirtualMachine not found")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)