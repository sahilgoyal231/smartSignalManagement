# Free Serverless Deployment Guide

This guide explains how to deploy the entire Smart Signal System (Microservices + Dashboard + Databases + Message Brokers) for **100% free** using Generous PaaS Free Tiers.

By following this guide, you will bypass the need for expensive Kubernetes clusters or heavy AWS EC2 instances.

---

## 1. Databases & Message Brokers (Free Tier)

Since we cannot run heavy databases on free VPS instances, we use fully managed serverless databases. Sign up for the following free tiers and copy their connection URLs into your `.env` file:

### PostgreSQL -> Supabase
1. Go to [Supabase](https://supabase.com/) and create a new project.
2. Go to **Project Settings > Database** and copy the Connection String (URI).
3. Set `POSTGRES_URL` in your `.env`.

### Redis & Kafka -> Upstash
1. Go to [Upstash](https://upstash.com/) and create a **Free Redis Database**.
   - Copy the URL into `REDIS_URL`.
2. In Upstash, switch to the **Kafka** tab and create a **Free Serverless Kafka Cluster**.
   - Copy the Bootstrap Server into `KAFKA_BOOTSTRAP_SERVERS`.
   - Copy the SASL Username/Password into `KAFKA_SASL_USERNAME` and `KAFKA_SASL_PASSWORD`.

### MQTT -> HiveMQ Cloud
1. Go to [HiveMQ Cloud](https://www.hivemq.com/mqtt-cloud-broker/) and create a Free cluster.
2. Set your `MQTT_BROKER_HOST`, `MQTT_BROKER_USER`, and `MQTT_BROKER_PASSWORD`.

### Time-Series DB -> InfluxDB Cloud
1. Go to [InfluxData](https://cloud2.influxdata.com/) and create a free tier account.
2. Generate an API Token with Read/Write access.
3. Set `INFLUX_URL` and `INFLUX_TOKEN`.

---

## 2. Deploy Cloud APIs (Render)

We have provided a `render.yaml` file in the root of the repository that automatically instructs Render to build and deploy your 6 FastAPI microservices as web services.

1. Create a free account on [Render.com](https://render.com/).
2. Click **New > Blueprint**.
3. Connect your GitHub repository.
4. Render will read the `render.yaml` and automatically spin up the `event-service`, `health-monitor`, `ota-service`, `priority-queue`, `route-engine`, and `vehicle-registry`.
5. **Important:** In the Render Dashboard, go to your Environment Groups and paste in all the variables from your `.env` file so the apps can connect to your Serverless Databases.

*(Note: On the free tier, Render spins down services after 15 minutes of inactivity. They will take ~30 seconds to wake up on the next request.)*

---

## 3. Deploy Dashboard (Vercel)

Vercel provides native, 100% free hosting for Next.js applications like our Dashboard.

1. Go to [Vercel.com](https://vercel.com/) and click **Add New > Project**.
2. Import your GitHub repository.
3. **Crucial Step:** During setup, set the **Root Directory** to `dashboard/`.
4. In the Environment Variables section, add any `.env` variables required by the frontend.
5. Click **Deploy**.

Within 2 minutes, your admin dashboard will be live on a `*.vercel.app` domain!

---

## Summary
You now have a fully operational, enterprise-grade traffic management system running globally without paying a single cent for infrastructure! 
