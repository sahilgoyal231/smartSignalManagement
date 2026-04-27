# Smart Signal: Production Runbook

This guide covers the **self-hosted production deployment** using AWS infrastructure, Kubernetes, and the full containerized stack. For the free serverless deployment, see [FREE_DEPLOYMENT.md](../FREE_DEPLOYMENT.md).

## Prerequisites
- `aws-cli` configured with Administrator access
- `terraform` v1.5+
- `kubectl` and `helm`

---

## 1. AWS Provisioning (Terraform)
Navigate to the `infra/terraform` directory to spin up the VPC, RDS database, ElastiCache (Redis), and EKS environment.

```bash
cd infra/terraform
terraform init
terraform plan -out=tfplan
terraform apply "tfplan"
```

Once complete, update your local kubeconfig to connect to the new cluster:
```bash
aws eks update-kubeconfig --region us-east-1 --name smart-signal-eks
```

---

## 2. Database & Redis Prep

Extract the RDS endpoint and ElastiCache Redis endpoint from the Terraform output. Inject these into your Kubernetes ConfigMap/Secrets prior to deploying.

### Required Config Values
| Source | Config Key | Example |
|--------|-----------|---------|
| RDS | `DB_HOST` | `smart-signal-rds.xxxxx.ap-south-1.rds.amazonaws.com` |
| ElastiCache | `REDIS_URL` | `redis://smart-signal-redis.xxxxx.cache.amazonaws.com:6379` |
| EMQX (self-hosted) | `MQTT_BROKER` | `mqtt-service.smart-signal.svc.cluster.local` |

*Note: You must manually run the Alembic database migrations from the `vehicle-registry` or `health-monitor` service before the background workers start.*

```bash
kubectl -n smart-signal exec -it <vehicle-registry-pod> -- alembic upgrade head
```

---

## 3. Kubernetes Deployment

Apply the manifests in the `infra/k8s/` directory.

```bash
cd ../k8s

# Apply ConfigMaps and Secrets first
kubectl apply -f 01-config.yaml

# Apply the backend core
kubectl apply -f vehicle-registry.yaml
kubectl apply -f route-engine.yaml
kubectl apply -f priority-queue.yaml
kubectl apply -f event-service.yaml
kubectl apply -f ota-service.yaml
```

Verify that all pods reach a `Running` state:
```bash
kubectl get pods -n smart-signal
```

---

## 4. Hardware Sideloading
Before an Edge Node can receive OTA updates from the cloud, it needs an initial bootstrap image containing the OS, Python runtime, and the `mqtt` bootloader.

1. Flash standard Raspberry Pi OS Lite (64-bit) to the SD card.
2. Clone this repository locally to the Pi.
3. Install dependencies: `pip install -r edge-node/requirements.txt`
4. Set `NODE_ID` and `MQTT_BROKER` in `/etc/environment`.
5. Run `sudo systemctl enable smartsignal-edge.service`.

Once the node comes online, it will connect to the `health-monitor` automatically and appear in the Dashboard.

---

## 5. First Firmware OTA
Once nodes show as "ACTIVE" in the Dashboard, you can compile the `edge-node/src/` stack into a tarball and upload it via the OTA Service.

```bash
tar -czvf release-1.0.0.tar.gz -C edge-node/src .
```
Upload via the dashboard UI routing to `http://<load-balancer-ip>:8004/api/v1/ota/releases`.
