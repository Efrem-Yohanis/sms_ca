# Kubernetes starter templates

These manifests are a starting point for the campaign and admin web apps. They
assume PostgreSQL is provided externally and shared by the two Django services.
They do not create PostgreSQL, Kafka, ingress controllers, TLS certificates,
the SMS sender, DLR receiver, status updater, scheduler, or Airflow.
The audience-upload claim requires a BP storage class that supports
`ReadWriteMany`; change it to a supported storage class or use approved object
storage if RWX volumes are unavailable.

## Before applying

1. Replace the example image names/tags, namespace, database host, and example
   DNS names in these manifests.
2. Build and push images to the cluster registry. Build `admin-ui` with
   `VITE_ADMIN_API_URL=https://admin-api.<your-domain>/api/v1`.
3. Create the namespace and secrets through your cluster's approved secret
   manager. Do not commit secret values. Required secret keys are
   `DB_PASSWORD`, `DJANGO_SECRET_KEY`, and `FIELD_ENCRYPTION_KEY`; use the same
   Django key and field encryption key for both backends. Add SMTP credentials
   if email flows are enabled.
4. Add Gunicorn to both backend requirements and build new images. The current
   image defaults use Django's development server; the deployments here use
   Gunicorn for production.
5. Configure the Ingress TLS secret and verify the backend has the correct
   allowed hosts and CORS origins.
6. Provide any required internal CA certificates to the campaign backend so
   Python Requests can validate the SMSC HTTPS endpoint. Do not disable TLS
   verification.

## Apply sequence

Create the namespace, config, and secret first. Run the campaign migration
job and wait for it to finish before applying the admin migration job, then
apply the workloads and ingress. For example:

```sh
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
# Create sms-platform-secrets with your approved secret manager.
kubectl apply -f campaign-migrate-job.yaml
kubectl wait -n sms-platform --for=condition=complete job/campaign-migrate --timeout=10m
kubectl apply -f admin-migrate-job.yaml
kubectl wait -n sms-platform --for=condition=complete job/admin-backend-migrate --timeout=10m
kubectl apply -f workloads.yaml
kubectl apply -f ingress.yaml
```

Review resource requests/limits, replica counts, network policies, autoscaling,
storage, backups, and cluster-specific ingress settings with the BP platform
team before production use.
