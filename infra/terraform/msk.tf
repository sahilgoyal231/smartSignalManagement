# ── MSK (Managed Streaming for Apache Kafka) ───────────────────────────────────

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "smart-signal-kafka"
  kafka_version          = "3.5.1"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.t3.small"
    ebs_volume_size = 50
    client_subnets  = module.vpc.private_subnets
    security_groups = [aws_security_group.kafka_sg.id]
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "PLAINTEXT"
      in_cluster    = true
    }
  }

  tags = {
    Environment = "production"
    Project     = "SmartSignal"
  }
}

resource "aws_security_group" "kafka_sg" {
  name        = "smart-signal-kafka-sg"
  description = "Allow inbound traffic from EKS to Kafka"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }
}
