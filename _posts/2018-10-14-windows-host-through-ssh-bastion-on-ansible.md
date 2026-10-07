---
layout: post
title: "Windows host through SSH bastion on Ansible"
date: 2018-10-14 22:09:00 +0000
permalink: /2018/10/14/windows-host-through-ssh-bastion-on-ansible/
categories: ["ansible", "ssh", "windows"]
description: "A use case I’ve been asked about a few times is to be able to connect to a Windows host through another bastion host. In the context of this post, a bastion host is “a server that is placed on the boundary of an internal network and provides access to this network from another external …"
---

A use case I’ve been asked about a few times is to be able to connect to a Windows host through another bastion host. In the context of this post, a bastion host is “a server that is placed on the boundary of an internal network and provides access to this network from another external network”.

[![](/assets/images/2018/10/AWS_Bastion.png)](/assets/images/2018/10/AWS_Bastion.png)

*Typical AWS Bastion Setup – [source](https://aws.amazon.com/blogs/security/how-to-record-ssh-sessions-established-through-a-bastion-host)*

Because a bastion host provides access to an internal network, great care must be taken to harden this host from malicious actors. The scope of this post is to not cover the hardening of this host but rather how to configure Ansible to use Windows hosts within an environment like this.

# Protocols

The main two protocols that are used for this scenario are SOCKS and SSH which are fairly well known and understood so I’ll briefly talk about them.

## SOCKS

When we talk about proxies, typically a standard HTTP proxy comes in mind that can forward HTTP requests from a client to another server that the proxy can reach. As WinRM is a HTTP protocol we can still use a HTTP proxy to route to our Windows host but this guide is about using SSH through a bastion host so it will ignore HTTP proxies. SOCKS stands for SOCKet Secure and the latest standard is SOCKS5 which will be used in this guide.

SOCKS is a proxy that routes traffic back and forth between a client and a server and acts as a middle man between the two. It tries to be as transparent as possible and transfers the packet to the client and server unmodified. This is unlike a HTTP proxy which forwards the the HTTP request and can include more in depth analysis of the HTTP request itself and act accordingly.

The SOCKS protocol does not encrypt or change your data during transit but utilising it with other protocols, like SSH, we can ensure any traffic on a public interface is encrypted.

## SSH

The special sauce in this mix is Secure SHel (SSH) that is used as the channel to transfer the SOCKS data from the Ansible host to the bastion host. SSH is fairly ubiquitous in today’s IT environment so I won’t bore you with the details of what is actually happening during this connection. Channeling the data over SSH gives us a few benefits, such as;

- Encryption of data as it goes through the public channel
- Use SSH keys for authentication, this does not negate the need for WinRM authentication but is used to protect the bastion host
- Server host verification
- Compression of data when running over a high latency network

A very basic outline of what this can looks like is;

[![](/assets/images/2018/10/bastion-socks-diagram.png)](/assets/images/2018/10/bastion-socks-diagram.png)

*Excuse my crude diagramming*

Unlike a simple Ansible to Windows host over WinRM connection, this scenario has multiple network boundaries that we need to be aware of. These boundaries include;

- Ansible to the SOCKS listener
  - The port this runs on is dependent on whatever port the listener was configured with, `-D <port>`
  - This data contains the WinRM payload encapsulated in a SOCKS packet, encryption is dependent on the WinRM/HTTP protocol
  - In this demo, this all runs on the loopback interface but the SOCKS/SSH client could also be on another host if needed
- SOCKS listener to the SSH client
  - An internal channel that is controlled by the SSH service
- SSH Channel
  - SSH traffic sent over an unsecured connection like the internet
  - All data is encrypted using the SSH protocol and is seen as normal SSH traffic
  - Typically this is done over port 22 but can be whatever is specified by the user
  - In this demo, this is the data sent over port `2222` on the loopback interface (VBox NAT port forwarding)
- SSH Server to the WinRM listener
  - The Bastion host acts as the Ansible controller and sends the WinRM traffic to the Windows host
  - For WinRM, this would be done over port `5985` (http) or `5986` (https)
  - The WinRM service sees the bation host as the source and has no idea of the SSH/SOCKS implementation behind it

Any responses from the Windows host are sent back through the same channel and everything should be transparent to the Ansible controller.

## PSRP/WinRM

I’ve spoken about WinRM and PSRP at lengths in [Demystifying WinRM](/2018/01/24/demystifying-winrm/) and [PowerShell emoting on Python](/2018/08/14/powershell-remoting-on-python/) so I won’t go into too much detail here. Basically WinRM is a HTTP protocol and uses a SOAP based API for communication between the client and the server. While encryption can and should be used with either HTTPS or Kerberos with AES256 encryption, it is not as simple to setup and use in comparison to SSH. Windows does offer a [Win32 port](https://github.com/PowerShell/Win32-OpenSSH) of OpenSSH that you can use today but it’s still fairly buggy and not currently compatible in Ansible.

As time goes on I expect to see WinRM decline in use but for the immediate and short term future it is here to stay.

# In Action

Now that we’ve gone over a high level overview of what is involved, let’s demonstrate this in action.

## Requirements

Here are the following applications that need to be installed for the demo;

- [Ansible v2.7+](https://www.ansible.com/)
- [pypsrp](https://github.com/jborean93/pypsrp)
- [Vagrant](https://www.vagrantup.com/)
- [VirtualBox](https://www.virtualbox.org/)

If you wish to just read the blog then this isn’t necessary but actually doing each step helped me to understand what is actually going on and I highly recommend it.

Once Vagrant and VirtualBox have been installed, pip can be used to install the Python dependencies;

```
# recommend you use a Virtual Environment for your testing
pip install virtualenv
virtualenv ansible-bastion
source ansible-bastion/bin/activate

# install the required Python packages
pip install ansible pypsrp requests[socks]
```

This installs Ansible, pypsrp, and a library for requests to support SOCKS proxies.

## Setting up the hosts

Once the pre-requisite applications have been installed, the next step is to setup the test environment. Create a file called `'Vagrantfile'` with the following content:

```
# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.define "bastion" do |bastion|
    ssh_pub_key = File.readlines("#{Dir.home}/.ssh/id_rsa.pub").first.strip
    bastion.vm.box = "centos/7"
    bastion.vm.network "private_network", ip: "192.168.50.10",
      virtualbox__intnet: true
    bastion.vm.network "forwarded_port", guest: 22, host: 2222, id: "ssh"
    bastion.vm.provision "shell",
      inline: "echo '192.168.50.11 windows-server' >> /etc/hosts"
    bastion.vm.provision "shell", privileged: false,
      inline: "echo #{ssh_pub_key} >> $HOME/.ssh/authorized_keys"
  end
  config.vm.define "windows" do |windows|
    windows.vm.box = "jborean93/WindowsServer2016"
    windows.vm.network "private_network", ip: "192.168.50.11",
      virtualbox__intnet: true
  end
end
```

This Vagrantfile will create two VMs with the following configurations;

- A Centos 7 host that acts as our bastion host
  - Has a NAT adapter with a forwarded SSH port bound to `2222` for external access
  - A VirtualBox internal network adapter set to an IP of `192.168.50.10`, any IP will do here
  - A manual entry in the hosts file that points to our Windows host IP
  - Our current user’s public key set as an authorized key for SSH logon, this isn’t strictly needed but it saves us from managing SSH password authentication
- A Windows Server 2016 host that is our intended target
  - Has a NAT adapter for Vagrant to configure but will not be used as part of the demo
  - A VirtualBox internal network adapter set to an IP of `192.168.50.11`, any IP will do as long as it matches the host entry on our bastion host

This scenario is not limited to a Centos 7 or Windows Server 2016 host, the main requirement is that the bastion host can resolve our Windows host and that bastion can then be accessed through SSH from our Ansible controller host. Once the file been created, start the Vagrant process with the command `'vagrant up'`.

[![](/assets/images/2018/10/vagrant-up-bastion.png)](/assets/images/2018/10/vagrant-up-bastion.png)

*Get a cup of coffee this could take awhile*

This step can take some time to complete as it will download the Vagrant boxes required and then setup the VirtualBox VMs. Once the hosts are setup, you should be able to connect to the bastion host over SSH with the command `'ssh -p 2222 vagrant@127.0.0.1'`. Otherwise to log on manually, open the VirtualBox console for the VM and logon with the username `vagrant` and password `vagrant`. To remove the VMs or to start again, run `'vagrant destroy'`.

The SSH connection is targeted towards `127.0.0.1:2222` due to how the VirtualBox NAT network adapter works. What happens is that it sets up a listener on the localhost and listens on the port configured (`2222`). Any requests to this port are then forwarded to the port on the VM (`22`). While our new Windows host also has a NAT adapter for Vagrant to use in its initial configuration, we will be ignoring that and pretend only the internal network adapter exists for this demo. This effectively means we cannot access that Windows host on our Ansible controller host but our bastion host can through the internal network that they are both connected to.

## Configuring the SSH Proxy

The next step is to setup the SSH proxy that exposes a SOCKS5 proxy to channel the WinRM requests through the bastion host. This can be as simple as running `'ssh -C -D 1234 -p 2222 vagrant@127.0.0.1'` in another session and keeping that running for the tests. To have something that runs in the background you can use SSH Multiplexing with ControlMaster. To setup the background connection run;

```
# any folder will do, as long as it is the same in ControlPath
mkdir ~/.ssh/cp
ssh -o "ControlMaster=auto" -o "ControlPersist=no" -o "ControlPath=~/.ssh/cp/ssh-%r@%h:%p" -CfNq -D 127.0.0.1:1234 -p 2222 vagrant@127.0.0.1
```

Let’s break this down a bit more;

- `-o "ControlMaster=auto"`: Allow multiplexing when possible
- `-o "ControlPersist=no"`: The master connection will be closed when the initial connection is also closed
- `-o "ControlPath=..."`: The path to the control socket, uses some substituted values to derive the filename but is configurable
- `-C`: Compress the data that goes over this channel, good for high latency networks
- `-f`: Run SSH in the background after the connection is setup
- `-N`: Do not execute a remote command
- `-q`: Quiet mode
- `-D 127.0.0.1:1234`: The bind address and port for the SOCKS proxy, the host address can be omitted which indicates the port should be available from all interfaces
- `-p 2222`: The remote port of our bastion host
- `vagrant@127.0.0.1`: The username and hostname of our bastion host

Once you have finished the connection and wish to close it, simply run `'ssh -o "ControlPath=~/.ssh/cp/ssh-%r@%h:%p" -O stop -p 2222 vagrant@127.0.0.1'`. This closes the background connection that’s stored at the `ControlPath` option based on the host we specified (our bastion host). You can substitute `'-O stop'` with `'-O check'` to check the status of a connection as well.

Creating a SOCKS proxy is not limited to OpenSSH, there are various applications out there that can also achieve this goal. OpenSSH was chosen in this guide as it is fairly universal when it comes to using Ansible.

## Connecting with Ansible

Once the proxy has been setup, the last step is to create an Ansible inventory that will use the SSH proxy to talk to the Windows host. The inventory would be set like Ansible is connecting directly to the Windows host but with the addition of the `ansible_psrp_proxy` variable that points to our SSH proxy server.

For this demo, create a file called `inventory.ini` with the following content:

```
[windows]
windows-server

[windows:vars]
ansible_user=vagrant
ansible_password=vagrant
ansible_connection=psrp
ansible_psrp_protocol=http
ansible_psrp_proxy=socks5h://localhost:1234
```

Instead of using the typical winrm connection plugin, we will try out the new [psrp](https://docs.ansible.com/ansible/latest/plugins/connection/psrp.html) plugin which exposes a variable that can define a proxy for Ansible to use. This can also be done with the winrm connection plugin but requires global environment variables to be set which is a lot more messy if you have different proxy requirements per host. Breaking down the proxy variable we can see that it’s split into 3 parts `<scheme>://<hostname>:<port>`;

- `scheme`: Set to either `socks5` or `socks5h`, the former means DNS resolution is done on the client while the latter means resolution happens on the bastion host
- `hostname`: The hostname of the SSH proxy, in this demo this is the same host as the Ansible controller
- `port`: The port the SSH proxy is listening on, corresponds to the `-D` argument when starting the proxy

I haven’t been able to test it, but if your SOCKS proxy server requires user authentication then the credentials would be specified like `socks5://user:pass@host:port`.

As the bastion host contains the hosts entry to resolve the Windows host, we use the `socks5h` schema, this should be typical of most scenarios. Once the inventory has been created, simply run `ansible -i inventory.ini windows -m win_ping` and watch it connect.

[![](/assets/images/2018/10/bastion-ansible.png)](/assets/images/2018/10/bastion-ansible.png)

*Successful connection*

Now that we can successfully connect Ansible to our Windows host through the bastion host, you can easily see that Ansible runs as normal with the exception of the proxy variable being set. I would love to have the actual SOCKS/SSH proxy set up as part of Ansible to get rid of that manual step but that’s a nice to have feature and not a must have.
