---
layout: post
title: "Using Packer to create Windows images"
date: 2017-11-23 22:30:15 +0000
permalink: /2017/11/23/using-packer-to-create-windows-images/
categories: ["ansible", "packer", "windows"]
description: "As part of my role as a developer for Ansible on everything Windows, I have a need to test my code on a wide variety of Windows and PowerShell versions. I ended up having a setup of the following to cover my bases; Windows Server 2008 64-bit (PowerShell 3.0) Windows Server 2008 R2 (PowerShell 3.0) …"
---

{% raw %}
![](/assets/images/2017/10/packer-vagrant.png)

As part of my role as a developer for Ansible on everything Windows, I have a need to test my code on a wide variety of Windows and PowerShell versions. I ended up having a setup of the following to cover my bases;

- Windows Server 2008 64-bit (PowerShell 3.0)
- Windows Server 2008 R2 (PowerShell 3.0)
- Windows Server 2012 (PowerShell 3.0)
- Windows Server 2012 R2 (PowerShell 4.0)
- Windows Server 2016 (PowerShell 5.1)

This allows me to test new modules and core functionality over all the supported PS versions (3.0-5.1) as well as test any OS specific components, the latter being quite troublesome.

As you can see this is quite a matrix of test hosts that I needed to manage and I ended up doing this myself. Creating and managing these images was an entirely manual process from start to finish and the end result was a collection of offline OVF files I had backed up online. Because this was a manual process I was repeatedly coming across the same issues such as;

- Wasting hours manually installing Updates and rebooting the server when ready
- Forgetting the some important steps required in the image creation which required in more work when starting a VM from an image, e.g. not installing the WMF 3.0 hotfix
- Older Windows versions were limited with what commands I could run to shrink the base image size and I kept on forgetting what the rules were
- I still had to manually run sysprep after restoring an image to clear the system configuration info and then create the new WinRM listeners
- I could not really share the work that I did with others very easily

Because of the effort involved I ended up having a collection of images which were over 6 months old and everytime I created a new VM with them, I would spend some time getting the new VM’s up to date or manually fixing things I missed in the image creation. I could have solved this by just creating a new set of images or trying to update the existing ones, but this was not a fun process so I kept on putting it off.

In the end what I decided that manually maintaining images would be too time consuming and I decided to find another solution. I could either find an existing set of images online and reuse those or I could automate the entire process from start to finish myself and just run that script every few months or so. There were some existing repo’s online I could use and just fork to cover what I required, the closest I could find was Matt Wrock’s [packer-templates](https://github.com/mwrock/packer-templates) Github repo and his excellent blog post [here](http://www.hurryupandwait.io/blog/creating-windows-base-images-for-virtualbox-and-hyper-v-using-packer-boxstarter-and-vagrant). Unfortunately I had a few issues with his implementation as it did not support OS’ older than 2012 R2 and there was a lot of duplication of code and configuration which made it hard to follow how it works.

In the end I decided to do the work myself and create a way to generate the images I required but to fit the following requirements;

- Can be run by anybody that has access to a host with Ansible and VirtualBox installed
- Works with Server 2008 all the way to Server 2016
- The image must be created without any manual steps, and the resulting image can be started by Vagrant and ready to use without any manual intervention
- Easy to make changes or add future images/features
- Produces an image that is as lightweight as can be

# End Result

The fruits of my labour can be found in the repo [packer-windoze](https://github.com/jborean93/packer-windoze), I’m still tweaking it as I go along but the current iteration probably won’t change dramatically anytime soon. You can find the actual Vagrant images by searching [jborean93](https://app.vagrantup.com/boxes/search?utf8=%E2%9C%93&sort=downloads&provider=&q=jborean93) on Vagrant Cloud.

![](/assets/images/2017/10/Screen-Shot-2017-10-30-at-8.45.47-am.png)

*You can tell they are mine due to my ugly mug staring right back at you*

You can skip the rest of the blog post if all you want is to use it (I won’t judge) but I will go in depth through how the process works and some of the challenges I came across.

If you want to continue along and wish to run the build process in packer-windoze, you will need to ensure your system has the following set up

- [Packer](https://www.packer.io/docs/install/index.html) \>= 1.0.0
- [VirtualBox](https://www.virtualbox.org/wiki/Downloads) \>= 5.1.12
- [Ansible](https://github.com/ansible/ansible) \>= 2.5 or devel
- The [packer-windoze](https://github.com/jborean93/packer-windoze) repo cloned down to a local folder

As of writing this, Ansible 2.5 has not been officially released, please clone the Ansible repo from GitHub and checkout to the devel branch. You can learn more about how to do this as well as about Ansible in general by reading [Managing Windows Server with Ansible](/2017/10/12/managing-windows-servers-with-ansible/).

# Enter Packer

![](/assets/images/2017/10/logo_packer.png)

When starting this project I really wanted to find a way to use Ansible to create the image from start to finish but I always came across the issue of how to interact with VirtualBox and spin up a brand new VM from nothing. I could have just run some commands using `VBoxManage` but any implementation based on that would have been fragile at best. I decided to look around to see what other tools were around that I could use, in the end I went with a product called [Packer](https://www.packer.io/). Packer is a tool from Hashicorp, who make other great tools like [Vagrant](https://www.vagrantup.com/) and in their words, Packer is

> an open source tool for creating identical machine images for multiple platforms from a single source configuration

By using Packer I gained the following for free;

- Interaction with VirtualBox to start a new VM from nothing
- The ability to in the future to use other providers like VMWare, Hyper-V, Parallels if I so desire
- Integration with Vagrant Cloud to automatically upload new images

# Generate Packer Template and Build Files

A lot of the Packer repo’s I’ve seen on Github all fall prey to having multiple `.json` files, one for each image generated. While this isn’t a major issue, I found that there was so much duplication between the different template files as well as the Windows answer files and I was hoping to remove this. My solution to this was to create an Ansible role that would generate the required Packer template and answer file required for each specific host type. This role will take in predefined variables for that host type, like where to download the evaluation ISO and what image name to set in the answer file, and generate it on the fly.

To generate these files run;

```bash
ansible-playbook packer-setup.yml -e man_packer_setup_host_type=<host type>
```

The var `man_packer_setup_host_type` corresponds to one of the host types that have been defined in the role, I’ll save you some trouble by giving you the current options here;

- `2008-x86`: Windows Server 2008 Standard 32-bit
- `2008-x64`: Windows Server 2008 Standard 64-bit
- `2008r2`: Windows Server 2008 R2 Standard
- `2012`: Windows Server 2012 Standard
- `2012r2`: Windows Server 2012 R2 Standard
- `2016`: Windows Server 2016 Standard

![](/assets/images/2017/10/Screen-Shot-2017-10-30-at-3.19.17-pm.png)

*Output for generating files for Server 2016*

Once the script has been run, a new folder will be created named to what was set under `man_packer_setup_host_type`. This folder contains 4 files

![](/assets/images/2017/10/Screen-Shot-2017-10-30-at-3.20.56-pm.png)

Here is what each file is for;

- `Autounattend.xml`: Attached to the new VM and is used by Windows setup to install Windows without asking the user what to do
- `bootstrap.ps1`: A script called after Windows is installed to setup WinRM and any other pre-requisites for Ansible
- `hosts.ini`: An Ansible inventory file that contains the required host entries and vars for the provisioning phase of Packer
- `packer.json`: The Packer definition that tells Packer how to setup the VM and what to do with that image once it is finished

Once these files are generated you are free to run Packer by running the command `packer build -force <host_type>/packer.json` where `<host_type>` is the host type you specified. Running this command will take quite some time so be prepared to run it in the background or get very comfortable in your chair.

By dynamically generating these files, I do trade off some ease of use and make things more complicated, but in the end I gain the following benefits;

- All the unique configure for each host type is in one location so I can easily compare without opening multiple files
- I am no longer limited to JSON and can use comments in definition to make it easier to understand what is happening
- If I have any pre-tasks required to be run before Packer starts I can do it in this phase, this is important for Server 2008 64-bit
- Any shared configuration like the username and password is now stored in one location and can easily be changed by passing in separate variables
- I don’t need to duplicate a Packer JSON and Windows Answer file when adding a new build, just need to tweak the host config in the role vars file instead and it will generate it for me

# Packer Components

To create an image with Packer, a template file is used to define the steps and configuration that is required. The template is written in JSON and must contain these three components;

- Builders: a set of plugins used to build the base image on a machine, in this case we use the virtualbox-iso plugin to create a VM from an ISO
- Provisioners: a set of actions the perform on the image after it has been built by the builder, we use this to install updates and streamline the Windows image
- Post-Processors: after the image is shutdown at the end of the provisioning phase, these plugins control what happens to the VM such as create a Vagrant box and upload it to Vagrant Cloud.

Here is an example `packer.json` file generated by packer-windoze for Server 2016;

```json
{
    "builders": [
        {
            "communicator": "winrm",
            "floppy_files": [
                "2016/Autounattend.xml",
                "2016/bootstrap.ps1"
            ],
            "guest_additions_mode": "disable",
            "guest_os_type": "Windows2016_64",
            "headless": false,
            "iso_checksum": "70721288bbcdfe3239d8f8c0fae55f1f",
            "iso_checksum_type": "md5",
            "iso_url": "http://care.dlservice.microsoft.com/dl/download/1/4/9/149D5452-9B29-4274-B6B3-5361DBDA30BC/14393.0.161119-1705.RS1_REFRESH_SERVER_EVAL_X64FRE_EN-US.ISO",
            "shutdown_command": "schtasks.exe /Run /TN \"packer-shutdown\"",
            "shutdown_timeout": "15m",
            "type": "virtualbox-iso",
            "vboxmanage": [
                [ "modifyvm", "{{.Name}}", "--memory", "2048" ],
                [ "modifyvm", "{{.Name}}", "--vram", "48" ],
                [ "modifyvm", "{{.Name}}", "--cpus", "2" ],
                [ "modifyvm", "{{.Name}}", "--natpf1", "winrm,tcp,127.0.0.1,55986,,5986" ]
            ],
            "winrm_insecure": true,
            "winrm_password": "vagrant",
            "winrm_port": "5986",
            "winrm_use_ssl": true,
            "winrm_username": "vagrant"
        }
    ],
    "provisioners": [
        {
            "command": "ansible-playbook main.yml -i 2016/hosts.ini -vv",
            "type": "shell-local"
        }
    ],
    "post-processors": [
        {
            "output": "2016/virtualbox.box",
            "type": "vagrant"
        }
    ]
}
```

I will explain more about each component below and what each of the keys mean.

## Builders

The first component that is run by Packer and is used to build a new machine and set it up so it is ready for provisioning. There are numerous plugins that can be used in this stage which govern where and how the host is actually created for the build process. You can build the image in AWS, a local VM using the VirtualBox, VMWare provider and so on. In packer-windoze we are are using the `virtualbox-iso` provider which takes in an ISO image and create a VM from that image.

Going through the template above, here is what each key does (note: some keys are specific to the `virtualbox-iso` type);

- `communicator`: The mechanism used by Packer to execute commands, by default the `SSH` communicator is used but we need `winrm`
  - This is only used to send the `shutdown_command` and sets Packer to monitor the `winrm_port` so it knows when to star the `Provisioners` component
- `floppy_files`: A list of files (relative to the `cwd`) to add to the floppy drive of the VM
  - This is seen under the `A:` drive during Windows setup and is how we start the Windows setup process with our `Autounattend.xml` file
- `guest_additions_mode`: We set to `disable` as we don’t care about installing the VirtualBox tools, this governs how the install ISO is accessed on the VM
- `guest_os_type`: The guest OS type that is being installed, to get the best performance this should be set to the OS we are creating
  - To view all the available values for the local install of VirtualBox, run `VBoxManage list ostypes`
- `headless`: Whether to show the console window during the Packer execution, this is set to `false` by default but it can be quite useful to set to `true` to debug any issues that may come up
- `iso_checksum`: The checksum for the ISO file, Packer will bail out if the checksum does not match the ISO specified at `iso_url`
- `iso_url`: Either a URL or local path to the Windows ISO to install, if it is a URL Packer will download it to a temporary directory
- `shutdown_command`: The command to run to shutdown the host after the full build process is complete (this is after the provisioning stage)
  - packer-windoze calls a scheduled task that will delete the WinRM listeners and then shutdown the host using this command
- `shutdown_timeout`: The amount of time to wait after `shutdown_command` is run before erroring out
- `type`: Tells packer that we are using the `virtualbox-iso` plugin
- `vboxmanage`: A list of commands to run before starting the VM
  - We set the CPU, RAM to make sure the build process is not abysmally slow
  - We also set a port forwarder so that Ansible can talk to the new Windows host during the provisioning component
- `winrm_insecure`: Tells packer to ignore any certificate errors when connecting to the HTTPS WinRM host
- `winrm_password`: The password for `winrm_username`
- `winrm_port`: The local port on Windows (not forwarded port) that is used to check when WinRM is active
- `winrm_use_ssl`: Use HTTPS (port 5986) instead of HTTP, Packer does not support message encryption over HTTP so we use HTTPS instead of disabling the message encryption check
- `winrm_username`: The local account that Packer connects with over WinRM to run remote commands like `shutdown_command`

While we are only using one builder with packer-windoze, it shouldn’t be too difficult to add support for another builder like VMWare as all it would take another entry in `builders` for the VMWare type.

### Windows Answer File – Autounattend.xml

When starting up the VM, a file called `Autounattend.xml` is placed at `A:\Autounattend.xml`, this is a special file which is used during the Windows setup process that tells Windows what to install and configure on the new host. Unfortunately Microsoft’s love of XML really becomes apparent here and this answer file can be quite verbose. On a basic level the answer file is split up into the following components

- `windowsPE`: Set’s the Windows PE environment used by the setup wizard such as language, disk/partition setup and install image name
- `generalize`: Set’s Sysprep and PnP info, this doesn’t play a big part in the setup process
- `oobeSystem`: Set’s box specific information such as username/passwords and logon commands
- `specialize`: Stops Windows from starting up annoying programs like the server manager on logon and so on

I’ll go into more details on the `windowsPE` and `oobeSystem` section as they configure most of the settings with Windows. Let’s start with the first section `windowsPE`, here is a snippet for Server 2016;

```xml
<component xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="Microsoft-Windows-International-Core-WinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
    <SetupUILanguage>
        <UILanguage>en-US</UILanguage>
    </SetupUILanguage>
    <InputLocale>en-US</InputLocale>
    <SystemLocale>en-US</SystemLocale>
    <UILanguage>en-US</UILanguage>
    <UILanguageFallback>en-US</UILanguageFallback>
    <UserLocale>en-US</UserLocale>
</component>
<component xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
    <DiskConfiguration>
        <Disk wcm:action="add">
            <CreatePartitions>
                <CreatePartition wcm:action="add">
                    <Type>Primary</Type>
                    <Order>1</Order>
                    <Size>350</Size>
                </CreatePartition>
                <CreatePartition wcm:action="add">
                    <Order>2</Order>
                    <Type>Primary</Type>
                    <Extend>true</Extend>
                </CreatePartition>
            </CreatePartitions>
            <ModifyPartitions>
                <ModifyPartition wcm:action="add">
                    <Active>true</Active>
                    <Format>NTFS</Format>
                    <Label>boot</Label>
                    <Order>1</Order>
                    <PartitionID>1</PartitionID>
                </ModifyPartition>
                <ModifyPartition wcm:action="add">
                    <Format>NTFS</Format>
                    <Label>Windows 2016</Label>
                    <Letter>C</Letter>
                    <Order>2</Order>
                    <PartitionID>2</PartitionID>
                </ModifyPartition>
            </ModifyPartitions>
            <DiskID>0</DiskID>
            <WillWipeDisk>true</WillWipeDisk>
        </Disk>
    </DiskConfiguration>
    <ImageInstall>
        <OSImage>
            <InstallFrom>
                <MetaData wcm:action="add">
                    <Key>/IMAGE/NAME </Key>
                    <Value>Windows Server 2016 SERVERSTANDARD</Value>
                </MetaData>
            </InstallFrom>
            <InstallTo>
                <DiskID>0</DiskID>
                <PartitionID>2</PartitionID>
            </InstallTo>
        </OSImage>
    </ImageInstall>
    <UserData>
        <ProductKey>
            <WillShowUI>OnError</WillShowUI>
        </ProductKey>
        <AcceptEula>true</AcceptEula>
        <FullName>Vagrant</FullName>
        <Organization>Vagrant</Organization>
    </UserData>
</component>
```

This example above does the following;

- Set the language and locale of the Windows setup wizard to `en-US`
- Create 2 partitions on the disk, 1 for the recovery/boot partition and the 2nd for the Windows OS
- Install Windows Server 2016 Standard on Disk 0 Partition 2
- Accept any EULA agreements and don’t set a product key

As part of the packer-windows `packer-setup.yml` playbook, the main component that changes depending on the OS host type is `ImageInstall.OSImage.InstallFrom.MetaData` as that is dependent on the OS version. The disk configuration is also different for Server 2008 as it does not need a recovery partition.

The second major component of the answer file is `oobeSystem`, here is the setup for the same Server 2016 setup;

```xml
<component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <InputLocale>en-US</InputLocale>
    <SystemLocale>en-US</SystemLocale>
    <UILanguage>en-US</UILanguage>
    <UserLocale>en-US</UserLocale>
</component>
<component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <NetworkLocation>Home</NetworkLocation>
        <ProtectYourPC>1</ProtectYourPC>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <HideLocalAccountScreen>true</HideLocalAccountScreen>
        <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
    </OOBE>
    <TimeZone>UTC</TimeZone>
    <UserAccounts>
        <LocalAccounts>
            <LocalAccount wcm:action="add">
                <Group>Administrators</Group>
                <DisplayName>vagrant</DisplayName>
                <Name>vagrant</Name>
                <Description>vagrant</Description>
                <Password>
                    <Value>vagrant</Value>
                    <PlainText>true</PlainText>
                </Password>
            </LocalAccount>
        </LocalAccounts>
        <AdministratorPassword>
            <Value>vagrant</Value>
            <PlainText>true</PlainText>
        </AdministratorPassword>
    </UserAccounts>
    <AutoLogon>
        <Enabled>true</Enabled>
        <Username>vagrant</Username>
        <Password>
            <Value>vagrant</Value>
            <PlainText>true</PlainText>
        </Password>
    </AutoLogon>
    <FirstLogonCommands>
        <SynchronousCommand wcm:action="add">
            <CommandLine>C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -Command "Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Force"</CommandLine>
            <Order>1</Order>
        </SynchronousCommand>
        <SynchronousCommand wcm:action="add">
            <CommandLine>C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -File a:\bootstrap.ps1 winrm-listener</CommandLine>
            <Order>2</Order>
        </SynchronousCommand>
    </FirstLogonCommands>
</component>
```

The example above does the following;

- Set the language and locale for the installed version of Windows to `en-US`
- Hides some post setup screens like connect to a wireless network or add an online account
- Sets the builtin Administrator password to `vagrant`
- Create a new local Administrator called `vagrant` with the password `vagrant`
- Set the new account called `vagrant` to automatically logon when the computer boots
- Have the `vagrant` account set the PowerShell execution policy to `Unrestricted` and then run the `bootstrap.ps1` script when it firsts logs on

Ultimately what this answer file does is install Windows onto the VM, create the necessary accounts and finally run the `bootstrap.ps1` script to setup up the host so that Ansible can connect to it.

### Bootstrapping Script – bootstrap.ps1

Now that we have a way to install Windows without manual intervention, we need a way to setup the new host so that Ansible can connect to it and run the provisioning process. This means that the host must have at least an install of PowerShell v3.0 and .NET 4.0 as well a an active HTTPS listener configured. From Server 2012 this is not too much of an issue as it comes with PS v3 or newer but on Server 2008 and 2008 R2, multiple components need to be upgraded before we can configure WinRM. The best way to achieve this is to create a script that is set in the `Autounattend.xml` file to run on first logon, in this case the script is called [bootstrap.ps1](https://github.com/jborean93/packer-windoze/blob/master/roles/packer-setup/files/bootstrap.ps1). This script needs to meet the following requirements;

- Support PowerShell 1.0, for core functions, as the evaluation ISO of Server 2008 is pre SP2 and only comes with PowerShell 1.0
  - Functions that download files, run processes, reboot and resume the script, need to support this version
- Have the ability to reboot and resume the script after the reboot automatically as most steps require a reboot to complete
- Give some form of logging to help debug any errors, this is because if the script fails there is no indication it failed as the console window automatically closes
- Support multiple OS types and architectures and download the required hotfixes for those OS’

The script itself is split up into separate actions defined in a `switch` statement, e.g. there is a single action called `dotnet` to update .NET to v4.5. At the end of the action, the script will call the `Reboot-AndResume` function and specify the next task under the `-action` parameter. This continues until `winrm-listener` is called and instead of rebooting, the script exits normally as we now have an active WinRM listener for Ansible to use.

The `Reboot-AndResume` function, is is designed to reboot the host and rerun the script with the action specified. While I believe this could be done natively in PowerShell, this featured required v3 or newer to be installed which in our case is not guaranteed. In the end I created a function to use the same technology as what the answer files use. Here is the function in the `bootstrap.ps1` script;

```powershell
Function Reboot-AndResume($action) {
    # need to reboot the server and rerun this script at the next action
    $command = "$env:SystemDrive\Windows\System32\WindowsPowerShell\v1.0\powershell.exe A:\bootstrap.ps1 $action"
    $reg_key = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
    $reg_property_name = "bootstrap"
    Set-ItemProperty -Path $reg_key -Name $reg_property_name -Value $command
    Write-Log -message "rebooting server and continuing bootstrap.ps1 with action '$action'"
    if (Get-Command -Name Restart-Computer -ErrorAction SilentlyContinue) {
        Restart-Computer -Force
    } else {
        # PS v1 (Server 2008) doesn't have the cmdlet Restart-Computer, use el-traditional
        shutdown /r /t 0
    }
}
```

The function will create a property under the registry key `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce` which, when Windows logs on with an account, will run the same script again but with the next action in line. This continues until there is no actions left to run and the WinRM listener is up and running. In a normal situation this may not be ideal as to achieve the automatic login on boot, the username and password must be set in plaintext in the registry. Because these are dev boxes where the passwords don’t matter it is an acceptable solution.

The script itself is designed to do as little work as possible and the end result is to just have a WinRM listener up and running. This is because debugging and error handling in this stage is quite difficult and because the output is not shown on the Packer console we cannot easily track the progress. This is why the majority of the setup is actually done in the provisioning stage with Ansible.

## Provisioners

Once Packer detects that WinRM is up and running, it knows that the build stage is complete and moves on to the provisioners component. In packer-windoze this is a simple local shell command `ansible-playbook main.yml -i <host_type>/hosts.ini -vv`. There is an `ansible` provisioner available where you can specify just the playbook file but it requires a custom connection plugin to be set up to enable Windows support. I preferred to use the inbuilt WinRM connection within Ansible as the custom connection plugin in my experience is broken in a few places. To use the `winrm` connection I just had to manually run the Ansible command through the local shell plugin.

The playbook `main.yml` currently has 6 roles that are run which are;

- `update`: Install all the updates that are available for the OS
- `personalise`: Configure the Windows profile to be more developer friendly and install useful tools
- `cleanup-winsxs`: Try and reduce the size of the WinSXS folder
- `cleanup-features`: If [Features on Demand](https://technet.microsoft.com/en-us/library/jj127275.aspx) is supported, remove all unused features
- `cleanup`: Remove any temp files, defrag the C drive and 0 out empty space for the image compression to be effective
- `sysprep`: Setup the sysprep process and shutdown scheduled task to be called by Packer

I’ll go into more details about each role below

### Updates

By far, one of the more complex roles that is being used. This role will ensure that all updates that match the categories `CriticalUpdates`, `SecurityUpdates`, `Updates`, `UpdateRollups`, and `FeaturePacks` are installed on the Windows host. To do this, I used the [win_updates](http://docs.ansible.com/ansible/latest/win_updates_module.html) module and specified those categories. When creating this role I came across the following issues

- Ansible does not support until loops on blocks or includes, makes it difficult to loop through call win_updates and rebooting after an update was installed
- Once all the `CriticalUpdates` are installed and I move onto `SecurityUpdates`, more `CriticalUpdates` may now be available and I would need to rerun it again for the previous categories
- Each call with WSUS takes a long time so I needed to minimize the number of times I called the API
- Running `win_updates` with all the categories above failed on older hosts as it was too much for it to handle, ended up splitting each task per category
- WUA is very temperamental and I came across transient errors that would not fail when running a second time
- When installing lots of updates and rebooting, Windows may reboot a second time but not before WinRM is active making Ansible think the host is ready
- Server 2008 kept on failing with the error C8000266, turning on verbose logging for WUA seemed to fix this

To bypass these issues I created a complex role which followed the following structure (you can click on it to unblurrify it);

[![](/assets/images/2017/10/Windows-Update-Flowchart.jpg)](/assets/images/2017/10/Windows-Update-Flowchart.jpg)

*Not the prettiest but it get’s the job done*

What this means is that there is a global var that states whether it believes there are no more updates available for that category. It loops from 1 to 10 and then loops through each category to run an update process. If it is the 3rd iteration and there are no updates available then it will set the global var for that category to say do not check for more updates in this category. This is repeated until the end of the 10th iteration where it will do one last check for all categories in case we missed any.

As I said complex and annoying but I’ve run it multiple times and it hasn’t let me down. There is work underway in Ansible for the 2.5 release to make this process a lot easier than it is today. This change will add in the functionality for Ansible to reboot the Windows host if a reboot is required and to continue installing updates until there is none left.

Once the changes have been made, this process should just be a simple task like;

```
- name: install all Windows Updates
  win_updates:
    category_names:
    - ...
    - ...
    state: installed
    reboot: yes
```

## Personalise

One of my common annoyances with Windows is the fact that it hides file extensions, does not show hidden files and folders in Windows Explorer, and it does not come with the very useful tools within [Sysinternals](https://docs.microsoft.com/en-us/sysinternals/) like `Procmon`, `Procexp`, and `PsExec`. I decided to make a role that can make these changes for me so I don’t have to enable it everytime. On the plus side, it also installs [Chocolatey](https://chocolatey.org/) which is a fantastic and easy to use package manager for Windows.

### Cleanup-Winsxs

Since Windows Server 2008 and Windows Vista, Microsoft has introduced the concept of `Windows Side by Side` and storing each Windows component as a separate package. From my limited understanding this has allowed Windows to keep multiple versions of a component within the same OS. When a new update is installed a new package is added to the folder `C:\Windows\WinSxs` and it will keep on growing as time comes. What this role does is try to cleanup as much of this component store as possible. Unfortunately, some of the older Windows versions don’t have a number of these functions so the effectiveness of the role can vary. Here is what it tries to run;

- `DISM.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase`
  - This is the best thing since sliced bread when it comes to cleaning up the WinSxS folder as it removes all the uneeded older components.
  - Unfortunately this is only available from Server 2012 R2 onwards
- `DISM.exe /Online /Cleanup-Image /SPSuperseded`
  - Cleans up older installs of service packs
  - Only available from Server 2008 R2 onwards
  - While we only install a service pack for 2008, which doesn’t support this command, it doesn’t hurt to run it anyway
- `compcln.exe /quiet`
  - Cleans up older installs of service packs
  - Only available for Server 2008, newer OS’ use the above command instead
- `cleanmgr.exe`
  - Only run for hosts that cannot run the DISM `/ResetBase` command
  - Not as effective as the DISM command but it does clear some older update components
  - Because Windows Server does not have `cleanmgr` setup by default, the role will copy the relevant binaries from the WinSxS folder and place them where it is required, this bypasses the need to install the Desktop Experience features

I’m hoping as time goes on I can find more effective ways to reduce the size of the WinSxS folder, especially for older hosts, but a lot of my issues stem from the fact that DISM only really became useful for this process from Server 2012 R2. I thought about slipstreaming the updates in the install ISO so that when Windows is installed only the latest components exists in the WinSxS folder and we don’t have to install any updates separately. This is a pretty big change and I think pretty hard to automate so it’s just a pipe dream right now.

### Cleanup-Features

By default, Windows ships with the majority of its features in the install even when they are not enabled by default. This means there is a lot of disk space being used for things that aren’t being used like the IIS components. To help alleviate this issue, Microsoft introduced the concept of `Features on Demand` in Server 2012. Features on Demand allows you to fully remove a feature that is not being used. Before you could only turn off a feature with the cmdlet;

`Remove-WindowsFeature -Name <feature name>`

Now you can use the new cmdlet with the `-Remove` command to completely remove a feature like;

`Uninstall-WindowsFeature -Name <feature name> -Remove`

The main disadvantage of this process is that it takes a longer time to enable a removed feature. This is because Windows needs to either source the feature files from Windows Update or from the source install media. In the end, the amount of space you save with this process outweighs the tradeoffs in this example and so I run it where possible.

### Cleanup

I also have a generic cleanup role which does the following

- Remove the pagefile and reboot the server
- Cleanup any temporary folders like `C:\Temp`, `C:\Windows\Temp`
- Clear out the WinSXS ManifestCache folder
- Defragment the drive, this is done to ensure the next step is more effective
- 0 out the empty space of the drive by creating one large file of 0 byte blocks and then finally removing it

The last step may seem weird but what it does is to create one large file that takes up the full space available on the hard drive. This data is just a binary file of 0 bits and removed once the whole drive is filled. This is done so that compression of the image, run after provisioning is complete, is able to compress all unused space. Without this, there would be sections in the image’s data with 1’s instead of 0’s and the compression process cannot compress that as easily.

None of these steps save a lot of space but altogether they can be quite useful and are better than nothing.

### Sysprep

The final role is the one which set’s up the sysprep process and what the new image will do once Vagrant starts it up. These are the tasks it runs;

- Ensure the directories `C:\Windows\Panther\Unattend` and `C:\temp` exist
- Download the [ConfigureRemotingForAnsible.ps1](https://raw.githubusercontent.com/ansible/ansible/devel/examples/scripts/ConfigureRemotingForAnsible.ps1) script to `C:\temp`
  - This is used during the Vagrant startup process to create the WinRM listeners
- Template out the `unattend.xml` file which is used by the sysprep process to generalise the Windows image without manual intervention
- Create a run once registry entry to run the sysprep process on the next startup (when Vagrant first starts up the image)
- Create a scheduled task which is used by Packer to remove the WinRM listeners and then shutdown the host
- Set a flag that tells Windows to recreate the pagefile after the next reboot (after the image is created)

I wrote this role so that the sysprep process is run when Vagrant starts up the image so that the evaluation timer is reset back to the maximum allowed when the image is created but this does not seem to be the case. I am planning on revisiting this so the sysprep process is run before the image is created to reduce the startup time needed for the Vagrant images.

## Post-Processors

Once the OS has been provisioned and shutdown, Packer will finally run the post-processors that are configured in the `packer.json` file. By default this is just a step to export the VM as a Vagrant box file called `vagrant.box`. I have added the ability to add a step to upload the newly created Vagrant image to the Vagrant Cloud. To create the Packer template with this ability run the below where you would replace the values in `<>` with whatever is relevant to your Vagrant Cloud account.

```bash
ansible-playbook packer-setup.yml -e man_packer_setup_host_type=2016 -e opt_packer_setup_access_token=<api_token> -e opt_packer_setup_version=0.0.1 -e opt_packer_setup_box_tag=<vagrant_cloud_box_tag>
```

# Problems

When creating this process I came across a few problems that either needed to be fixed or bypassed. Some of these problems still exist today but I am planning on trying to fix them as time goes on.

## JSON and Comments

One of the main things I disliked about Packer was that the config files are in JSON. While JSON is a lot simpler than XML I find the fact you cannot add comments into the file very annoying and makes it harder for new people to understand why you did what you did. This was one of the primary drivers of moving the Packer configuration to a YAML file which Ansible uses to produce the final JSON file used by Packer.

## Reboot

A major issue when it came to using Ansible with Packer was that you could not reboot the host without setting up a local only network adapter for the VM. This is because Packer uses a NAT network adapter with forwarded ports as the default network adapter to use in VirtualBox. This is a problem as the older reboot behaviour for Ansible was to;

- Send the shutdown command over WinRM
- Wait until the WinRM port is not reachable (host is shutdown)
- Wait until the WinRM port is reachable (host is back up)
- Run a test command to ensure the host is back online and ready

When the port is forwarded by VirtualBox, the WinRM port will never go down as VirtualBox is still active and listening on that port even if Windows is not.

One solution I started with was to also create a host only network adapter and get Ansible to communicate over that one. I was able to successfully set this up but I was unhappy with the solution as it required that network adapter to actually exist beforehand and made things more complicated when it came to reserving IP addresses.

The final solution was to fix up the Ansible code to actually work in situations where the port is being forwarded by another device. I raised a pull request to change the reboot behaviour to;

- Get the system boot time
- Send the shutdown command over WinRM
- Change the connection timeout value to something really low like 5 seconds
- Keep on getting the system boot time until it is different from step 1, ignore any connection errors as the host may be offline
- Run a test command to ensure the host is back online and ready

With these changes, Ansible no longer uses the port to determine whether the host actually rebooted but uses the system boot time instead. These changes have been merged into the devel branch and will be made available in the 2.5 release. Until that time you can use checkout the devel branch and run `source hacking/env-setup` to use the pre-release code.

## Installing Windows Updates

Installing Windows Update over WinRM has always been an issue due to the restrictions that Microsoft has placed on a Network logon session. Ansible makes it easier by having a module [win_updates](http://docs.ansible.com/ansible/latest/win_updates_module.html) that run the relevant WUA calls in a scheduled task so you don’t have to do it yourself. This is similar to the `elevated_user/password/command` process that Packer has for running “elevated” commands. While the module makes it easier to actually install the updates I still had the following issues;

- To reboot after the updates are installed, a separate Ansible task calling `win_reboot` is needed
- You cannot use an `until` loop over multiple tasks in Ansible right now which makes it impossible to loop these 2 tasks until no updates are left
- Scheduled tasks can be problematic when it comes to starting up and I had a few issues when it came to Ansible trying to create/start the scheduled task

Like the reboot issues, I’ve raised a few pull requests in the Ansible repo to update the `win_updates` task to;

- Get Ansible to automatically use the [become](http://docs.ansible.com/ansible/latest/become.html) process when executing the `win_updates` module
  - This removes the need for running with a scheduled task as become on Windows means the process runs under an interactive logon session
- Convert the `win_updates` module to an action plugin which automatically reboots the host when required and continues to install updates until there is nothing left
  - This removes the need for the convoluted workflow that currently exists in the update role

The first PR has been merged into Ansible while the 2nd one is in review but should be in relatively shortly. Like the `win_reboot` changes, these features should be available in the 2.5 release or in the devel branch right now.

## Sourcing Evaluation ISOs

Microsoft makes it easy today to get the evaluation ISOs for the newer OS’. You can currently get the Server 2012, 2012 R2 and 2016 evaluation ISO from the [Microsoft Evaluation Centre](https://www.microsoft.com/en-us/evalcenter/) which makes them easy. Server 2008 and 2008 R2 are a bit different where they are not in the evaluation centre but are still available by doing a quick google search. Server 2008 makes it even more difficult by only offering an ISO based on the RTM release and not on SP2 which is required by Ansible (see below for more 2008 woes).

## Server 2008

Ahh Server 2008, how I loathe thee. Still supported by Microsoft until 2020 but different enough it requires some special handling to get it working. Here are some of the differences/use cases I needed to handle to get this process working for this OS version-;

- 2008 comes in a 32-bit variant, this means the unattend.xml files used in the install and sysprep process needed to dynamically change the architecture string used to support 32-bit
- The unattend.xml is not completely different from the other OS’ but different enough to warrant some head banging to get things working properly on this version
- The 2008 evaluation ISO does not come preloaded with SP2, this needed to be manually installed in the bootstrapping process so that PowerShell 3.0 could then be installed
- The base image only came with PowerShell 1.0 which needed to be upgraded to 2.0 before 3.0 could be installed, this also meant the bootstrapping script needed to support the 1.0 version for the majority of its steps
- The Internet Explorer 9 update does not play nice with the Ansible `win_updates` module, I had to manually install this update in the bootstrapping process so it wouldn’t fail later on

Once I got through these issues, the end result is a working image for Server 2008 but due to the age of the OS, it still has further limitations when it comes to what it can do. The only reason why I included this version is because it is still supported by Microsoft and Ansible and I needed a way to test on this version without manually creating an image for it.

# Looking to the Future

This project is definitely not complete and I picture having to change some of these processes as time goes on and bugs are found. A few things I know off already that I want to change/add are;

- Re-arrange the sysprep process to run before the image is created
- Get the sysprep process to re-arm the evaluation key so the full evaluation period is available when Vagrant starts up
- Setup the registry keys to enable TLSv1.1 and TLSv1.2 on Server 2008 R2
- Add the ability to create an image for Windows Nano Server
- Add the ability to create an image for Windows 10

As with everything, it will take some time to implement some of the things above but feel free to raise a PR on [packer-windoze](https://github.com/jborean93/packer-windoze) if you’ve done the hard yards.
{% endraw %}
