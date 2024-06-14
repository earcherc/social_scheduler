```bash
gcloud functions deploy twitter_uploader \
--runtime python310 \
--trigger-http \
--entry-point main \
--timeout 60s \
--memory 128MB \
--region us-west2 \
--source ./twitter_uploader
```

```bash
gcloud functions deploy drive_watcher \
--runtime python310 \
--trigger-http \
--entry-point main \
--timeout 60s \
--memory 128MB \
--region us-west2 \
--source ./drive_watcher
```