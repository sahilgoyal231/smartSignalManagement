# ── EKS Cluster ────────────────────────────────────────────────────────────────

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "19.16.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.28"

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = true

  eks_managed_node_group_defaults = {
    ami_type = "AL2_x86_64"
  }

  eks_managed_node_groups = {
    general = {
      name = "general-compute"

      instance_types = ["t3.medium"]

      min_size     = 2
      max_size     = 5
      desired_size = 3
    }
  }

  tags = {
    Environment = "production"
    Project     = "SmartSignal"
  }
}
