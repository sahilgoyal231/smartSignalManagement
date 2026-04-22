# ── RDS PostgreSQL ─────────────────────────────────────────────────────────────

module "db" {
  source  = "terraform-aws-modules/rds/aws"
  version = "6.1.1"

  identifier = "smart-signal-db"

  engine               = "postgres"
  engine_version       = "15.4"
  family               = "postgres15"
  major_engine_version = "15"
  instance_class       = "db.t4g.micro"

  allocated_storage     = 20
  max_allocated_storage = 100

  db_name  = "smartsignal"
  username = "postgres_user"
  port     = 5432
  password = var.db_password

  multi_az               = false
  db_subnet_group_name   = module.vpc.database_subnet_group
  vpc_security_group_ids = [aws_security_group.db_sg.id]

  # For demonstration/development purposes
  skip_final_snapshot = true
  deletion_protection = false

  tags = {
    Environment = "production"
    Project     = "SmartSignal"
  }
}

resource "aws_security_group" "db_sg" {
  name        = "smart-signal-db-sg"
  description = "Allow inbound traffic from EKS"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }
}
