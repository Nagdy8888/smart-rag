# Rebuildable encrypted IMDSv2 EC2 origin. No aws_key_pair and no SSH ingress.
# User-data starts Compose from /opt/smart-rag after SSM copies files.

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_eip" "origin" {
  domain = "vpc"
  tags = {
    Name = "${var.project_name}-origin"
  }
}

resource "aws_instance" "staging" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.origin.id]
  iam_instance_profile   = aws_iam_instance_profile.staging.name
  user_data              = file("${path.module}/user-data.sh")
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 80
    encrypted             = true
    delete_on_termination = true
  }

  ebs_block_device {
    device_name           = "/dev/sdf"
    volume_type           = "gp3"
    volume_size           = 50
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "${var.project_name}-origin"
  }
}

resource "aws_eip_association" "origin" {
  instance_id   = aws_instance.staging.id
  allocation_id = aws_eip.origin.id
}
