---
layout: post
title: "Decrypting the secrets of Ansible Vault in PowerShell"
date: 2018-05-20 05:49:40 +0000
permalink: /2018/05/20/decrypting-the-secrets-of-ansible-vault-in-powershell/
categories: ["ansible", "powershell", "windows"]
description: "Ansible Vault is a pretty nifty tool that allows people to easily encrypt secrets for use in Ansible. It’s a builtin tool that can be use to encrypt secrets and make them easily usable for Ansible. When calling Ansible, you must supply the password by either manually entering it or use a password file. From …"
---

Ansible Vault is a pretty nifty tool that allows people to easily encrypt secrets for use in Ansible. It’s a builtin tool that can be use to encrypt secrets and make them easily usable for Ansible.

When calling Ansible, you must supply the password by either manually entering it or use a password file. From there, Ansible will automatically decrypt the contents when it is required, simple stuff.

As an example I can turn something like this

```
host_password: supersecretpass123!
```

into this

```
$ANSIBLE_VAULT;1.1;AES256
33343835306666636239373663396363643766613363343837646633343933376633323964663030
3134616235646661306436643134383333633730376233650a663466323032343633383061336461
36393261363338616337613039363435313631343437323164386661326633313339396238396236
3462393338636632650a653036663266373533343232393838343161396564333963643632653932
30386135636131656130346537356637396139323134386162306431376564346537633566666532
6331323061373237336639356165393563613765663864366231
```

As a dev on the Ansible project, this was an area that I didn’t really understand and I wanted to fix that by understanding how the vault works. At the same time I also wanted to have another way for people working on Windows to encrypt and decrypt vault files, reducing the barrier for using Ansible for those users. Currently Ansible, and by extension `ansible-vault`, is unable to run natively on Windows. There are ways around this such as using WSL or Cygwin to run the Ansible scripts but either this won’t work for all users (WSL) or is quite complex to setup (Cygwin).

I decided to try and kill 2 birds with 1 stone, which was to re implement the functionality of `ansible-vault` in another language. In doing so I gain an understanding of how `ansible-vault` works as well as giving Windows users a native solution for managing vault files.

Before I started to write this new tool, I had a few goals in mind which were;

- Runs natively on Windows with no extra software dependencies
- Also works on older Windows hosts like Windows 7, 8, and 8.1
- Simple and easy to setup/use
- Easy to maintain the software going forward

I could have just ported the Python code to a script that works on Windows and be done with it but, in my mind, that would be cheating and doesn’t really fulfill all my goals. Specifically it would require Python to be installed (not a hard ask I know but still extra software) and I wouldn’t be learning too much if I just reused code from the Ansible codebase.

The result is a PowerShell module that includes cmdlets to encrypt and decrypt vault files but before I go into the PowerShell side I want to explain how Ansible Vault works based on what I learnt.

# Analysing Ansible Vault

The code behind Ansible Vault is all open source and can [viewed in the Ansible GitHub Repo](https://github.com/ansible/ansible/blob/devel/lib/ansible/parsing/vault/__init__.py) by anyone. At the time of writing this blog post, AES256 at the 1.1/1.2 implementation was the latest and that is what this section will break down. Each vault is split into 2 main parts;

- Header – On the first line of the vault file and defines the structure of the vault
- Cipher text – Contains the salt, hmac hash, and the encrypted bytes as a hex string with a newline at every 80 chars

## Header

The header of the vault is comprised of a few keys fields, each separated by `;`, which are;

- The file format ID, currently only `$ANSIBLE_VAULT` is used
- The vault version that indicates how it was encrypted
- The cipher used for encryption
- An optional ID field

### Versions

There are 3 versions of the Ansible Vault that exist;

- `1.0` – Introduced in Ansible 1.5, this is the original vault format and no longer in use
- `1.1` – Introduced in Ansible 1.5.1, fixed issues with the original format and is still in use today
- `1.2` – Introduced in Ansible 2.4, is the same as `1.1` but includes the `ID` field in the header

Currently `1.1` is used when no ID is set to the vault and `1.2` is used when an ID set. The cipher contents and encryption process are the same between the two, the only difference is the extra field in the header. Because the `1.0` format was quickly removed in a single minor release, I did not implement support for decrypting that format. If you still have a vault file in that format, change it immediately!

### Ciphers

The next field in the header is the cipher that is used, currently it can be either of the following;

- `AES` – Used in the `1.0` version and no longer in use
- `AES256` – Used in both `1.1` and `1.2`, is based on the AES cipher with a 256 bit key in CTR mode

This made thing relatively simple as there is only cipher I needed to add support for.

### Vault ID

The vault ID was added in the `1.2` version and it is used by Ansible to map a password to a particular vault file. For example, a user can create a vault file for each environment, say `dev`, `uat`, `prod`, and create a vault file for each environment with different passwords per ID/environment. When a vault file contains an ID, the header would look like the following;

```
$ANSIBLE_VAULT;1.2;AES256;prod
```

## Cipher Text

Before breaking down the cipher text, I will briefly cover the various cryptography tools used as part of the vault process. Currently these functions/protocls are being used;

- AES block cipher with a 32-byte (256 bit) key in CTR mode to encrypt/decrypt
- PBKDF2 using HMAC SHA256 to derive the various keys, this takes in a 32-byte salt, runs for 10000 iterations
- HMAC using SHA256 to verify the KDF output against the encrypted bytes
- PKCS7 padding on the encrypted bytes

When bringing this all together we need the following bits of information;

- A password used as the secret input into the PBKDF2 function
- A 32-byte salt to use with the password in the PBKDF2 function
- A 32-byte key to use as part of the HMAC function
- A 32-byte key used to initialise the AES cipher
- A 16-byte key used as the base counter/nonce of the AES CTR mode

We already know the password and the salt is stored in the cipher text, from there we can get the rest of the keys as they are the output of the PBKDF2 function. To get the salt, lets first break down the cipher text (excluding the header). Here is a sample cipher text that I posted in the beginning of this blog;

```
33343835306666636239373663396363643766613363343837646633343933376633323964663030
3134616235646661306436643134383333633730376233650a663466323032343633383061336461
36393261363338616337613039363435313631343437323164386661326633313339396238396236
3462393338636632650a653036663266373533343232393838343161396564333963643632653932
30386135636131656130346537356637396139323134386162306431376564346537633566666532
6331323061373237336639356165393563613765663864366231
```

This is a hex encoded string that contains the salt, the SHA256 based HMAC output of the encrypted bytes, and finally the encrypted bytes. Each entry is split by a newline which in hex form is `0a`, applying this split this is what we get;

```
# Salt
33343835306666636239373663396363
64376661336334383764663334393337
66333239646630303134616235646661
30643664313438333363373037623365

# HAMC
66346632303234363338306133646136
39326136333861633761303936343531
36313434373231643866613266333133
39396238396236346239333863663265

# Encrypted Bytes
65303666326637353334323239383834
31613965643339636436326539323038
61356361316561303465373566373961
39323134386162306431376564346537
63356666653263313230613732373366
39356165393563613765663864366231
```

Each entry is actually a hex string of a hex string, I’m not sure why this has been hex encoded twice but that’s just how it is. When “un-hexified” we get the following hex values for each entry;

```
# Salt (32 bytes)
34850ffcb976c9ccd7fa3c487df34937
f329df0014ab5dfa0d6d14833c707b3e

# HMAC (32 bytes)
f4f20246380a3da692a638ac7a096451
6144721d8fa2f31399b89b64b938cf2e

# Encrypted Bytes (48 bytes)
e06f2f75342298841a9ed39cd62e9208
a5ca1ea04e75f79a92148ab0d17ed4e7
c5ffe2c120a7273f95ae95ca7ef8d6b1
```

Bingo, we know have the salt and password and can use that in conjunction with the PBKDF2 function to produce the remaining keys. PBKDF2 is a key derivation function that applies a pseudorandom function to a secret input, such as a password, along with a salt to produce a derived key. Part of this function is the ability to specify the number of iterations that repeats the process to make the computational cost of calculating the key more expensive. As shown on [Wikipedia](https://en.wikipedia.org/wiki/PBKDF2), PBKDF2 has five input parameters

```
DK = PBKDF2(PRF, Password, Salt, c, dkLen)
```

where:

- `PRF`: is a pseudorandom function like a HMAC, for Ansible Vault this uses the SHA256 algorithm
- `Password`: the password/secret that is known to the user
- `Salt`: the salt, this is randomly generated when creating the vault but stored as part of the cipher text of an existing vault as we saw above
- `c`: the number of iterations desired, Ansible Vault is set to 10000
- `dkLen`: the length of output key, for Ansible Vault we want 80 as (80 == (32 + 32 + 16) == (AES Key + HMAC Key + CTR Counter/Nonce))

Putting this into practice, you can use this handy Python script to generate the derived key. Note: for this to work you need the [cryptography](https://pypi.org/project/cryptography/#description) package installed;

```
import binascii

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

password = b"password"  # this is the password I used to create the example vault
kdf = PBKDF2HMAC(
    algorithm=hashes.SHA256(),
    length=80,
    salt=binascii.unhexlify("34850ffcb976c9ccd7fa3c487df34937f329df0014ab5dfa0d6d14833c707b3e"),
    iterations=10000,
    backend=default_backend())
derived_key = kdf.derive(password)
print(binascii.hexlify(derived_key))
```

The output of this script is the following hex string;

```
# KDF (80 bytes)
fc4a21fb71bfaad6a0bbb078f0704721
ccad80519fc349c3ff14268fced14203
9bfb1a43effdfb8f8d7119387fccec54
8859c7fccc26589a65a2ee856e05763f
394f9f4a44152b33234cba44c930921b
```

Ansible Vault, splits this output at 32 and 64 bytes into 3 parts like so;

```
# AES Key (32 bytes)
fc4a21fb71bfaad6a0bbb078f0704721
ccad80519fc349c3ff14268fced14203

# HMAC Key (32 bytes)
9bfb1a43effdfb8f8d7119387fccec54
8859c7fccc26589a65a2ee856e05763f

# AES CTR Counter/Nonce (16 bytes)
394f9f4a44152b33234cba44c930921b
```

Now we know all the keys that are required to decrypt/encrypt the bytes but before we do that, we want to verify the HMAC output against what is expected. If the HMAC value does not match the expectation, we know the password/secret was incorrect and can report that back to the user. Using a simple Python script we can get the HMAC value of the encrypted bytes

```
import binascii
import hashlib
import hmac

key = binascii.unhexlify("9bfb1a43effdfb8f8d7119387fccec548859c7fccc26589a65a2ee856e05763f")
encrypted_bytes = binascii.unhexlify("e06f2f75342298841a9ed39cd62e9208a5ca1ea04e75f79a92148ab0d17ed4e7c5ffe2c120a7273f95ae95ca7ef8d6b1")

hmac_digest = hmac.new(key, encrypted_bytes, digestmod=hashlib.sha256).digest()
print(binascii.hexlify(hmac_digest))
```

This produces the result `f4f20246380a3da692a638ac7a0964516144721d8fa2f31399b89b64b938cf2e` which matches the HMAC value stored in the vault. We know the secret was correct and we can move onto decrypting the bytes themselves.

To decrypt the bytes, we need to use AES in CTR mode, here is some Python code to decrypt the data;

```
import binascii
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

key = binascii.unhexlify("fc4a21fb71bfaad6a0bbb078f0704721ccad80519fc349c3ff14268fced14203")
nonce = binascii.unhexlify("394f9f4a44152b33234cba44c930921b")
encrypted_bytes = binascii.unhexlify("e06f2f75342298841a9ed39cd62e9208a5ca1ea04e75f79a92148ab0d17ed4e7c5ffe2c120a7273f95ae95ca7ef8d6b1")

aes_cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), default_backend())
decryptor = aes_cipher.decryptor()
plaintext = decryptor.update(encrypted_bytes) + decryptor.finalize()
print(plaintext)
```

This produces the following UTF-8 string;

```
host_password: supersecretpass123!\n\r\r\r\r\r\r\r\r\r\r\r\r\r
```

So close to the plaintext but now we have `\r` padded onto the end of the string. This is just simple PKCS7 padding to make sure the input to the AES cipher is a multiple of the AES block size (16 bytes). This padding is the same byte where the decimal value of that byte is the number of bytes needed. In the case above, the length of the plaintext value (including the last newline) is 35 while the nearest full block is 48. To reach the full block size of 48, the byte with a decimal value of 13 (`\r`) needs to be appended. After removing the padding we get the original plaintext which Ansible loads as required.

To encrypt a string, it’s pretty much the same process in reverse order. For example this is what Ansible does when it goes to encrypt a string;

1.  Pad the text using the PKCS7 mechanism to the block size of 16 (AES block size / 8)
2.  Generate a secure random 32-byte salt to use in the PBKDF2 function
3.  Generate the AES, HMAC, and AES CTR counter/nonce bytes using the PBKDF2 function with the salt and password specified
4.  Encrypt the padded text text using AES in CTR mode with the keys produced in step 3
5.  Generate the HMAC SHA256 hash of the encrypted bytes based on the HMAC key from step 3
6.  Create a hex string of the salt, HMAC hash, and encrypted bytes
7.  Join the three hex string’s with a newline
8.  Create another hex string of the value from step 7
9.  Create the vault header and append the value from step 8

From there you have an Ansible Vault that is securely protected by a password of your choosing.

# Working with Windows

So now we know how the vault works and how Ansible encrypts/decrypts the data, it should be fairly trivial to reimplement it in PowerShell, or so I thought.

## Problems on Windows

The biggest issue I had with Windows was finding a way to interop with the functions that are being used in the Ansible Vault process. More specifically I needed a way to;

- Use PBKDF2 with the SHA256 algorithm
- Use AES in CTR mode
- Pad and unpad the decrypted bytes with the PKCS7 spec

Each one of the above is either not possible in the standard .NET framework that PowerShell uses, or requires a newer version of the framework. Let’s break down each part and how I ultimately implemented it in PowerShell.

### PBKDF2 with SHA256

The first step in implementing Ansible Vault on Windows is to derive the keys used in the downstream process. A quick Google search on how this can be done leads me to the [Rfc2898DeriveBytes](https://msdn.microsoft.com/en-us/library/system.security.cryptography.rfc2898derivebytes.aspx) class. The description for this class is

> Implements password-based key derivation functionality, PBKDF2, by using a pseudo-random number generator based on HMACSHA1.

Unfortunately we need to the use SHA256 hash in our generator so the default of SHA1 won’t produce the right key that we need. There’s some constructors that have a [HashAlgorithmName](https://msdn.microsoft.com/en-us/library/system.security.cryptography.hashalgorithmname.aspx) parameter so that looks like what we need.

[![](/assets/images/2018/05/Rfc2898DeriveBytesHashAlgorithmName.png)](/assets/images/2018/05/Rfc2898DeriveBytesHashAlgorithmName.png)

*What the, the docs says there is!*

So that didn’t work, when reading the docs around that constructor I found this gem

> Version Information  
> .NET Framework  
> Available since 4.7.2

So I either need to set a dependency on .NET 4.7.2 to run the cmdlets or find some other way around this limitation, because my goal was to support older hosts I pretty much had to find another way. The fact that a newer version of the .NET framework exposes the parameter that I needed usually means Windows can do it with the native Win32 APIs. After some searching I came across [this](https://blogs.msdn.microsoft.com/dsnotes/2017/09/20/pbkdf2-net-api-does-not-exists-with-sha256-implementation-here-pbkdf2-stands-for-password-based-key-derivation-function-2/) blog post from Microsoft which used the [BCryptKeyDerivation](https://msdn.microsoft.com/en-us/library/windows/desktop/hh448506.aspx) Win32 API. This is close to what I am looking for but unfortunately `BCryptKeyDerivation` was only added in Windows 8/Server 2012 and I was hoping for something I can use in Windows 7/Server 2008 R2. Finally I came across the [BCryptDeriveKeyPBKDF2](https://msdn.microsoft.com/en-us/library/windows/desktop/dd433795.aspx) which was added in Windows 7/Server 2008 R2.

So now we have an API available on Windows that can give us the key required but we need a way to call this within PowerShell. There’s no inbuilt way in PowerShell to do this, but you can use C# code with P/Invoke to call these platform functions and PowerShell can compile/run C# code. This is done through the [Add-Type](https://docs.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/add-type?view=powershell-6) cmdlet which calls `csc.exe` to compile the C# code and load it into the current PowerShell scope. For example here is a simple way to add the functions we need in PowerShell;

```
Add-Type -Namespace Win32 -Name NativeFunctions -MemberDefinition @'
[DllImport("Bcrypt.dll")]
public static extern uint BCryptOpenAlgorithmProvider(
    out IntPtr phAlgorithm,
    [MarshalAs(UnmanagedType.LPWStr)] string pszAlgId,
    [MarshalAs(UnmanagedType.LPWStr)] string pszImplementation,
    UInt32 dwFlags);

[DllImport("Bcrypt.dll")]
public static extern uint BCryptDeriveKeyPBKDF2(
    IntPtr hPrf,
    [MarshalAs(UnmanagedType.LPWStr)] string pbPassword,
    UInt32 cbPassword,
    byte[] pbSalt,
    UInt32 cbSalt,
    UInt64 cIterations,
    byte[] pbDerivedKey,
    UInt32 cbDerivedKey,
    UInt32 dwFlags);

[DllImport("Bcrypt.dll")]
public static extern uint BCryptCloseAlgorithmProvider(
    IntPtr hAlgorithm,
    UInt32 dwFlags);
'@

$algo = [IntPtr]::Zero
$res = [Win32.NativeFunctions]::BCryptOpenAlgorithmProvider([Ref]$algo, "SHA256", $null, 0x00000008)
if ($res -ne 0) {
    throw "Failed to open algo provider"
}

$key = New-Object -TypeName byte[] -ArgumentList 80
$salt = New-Object -TypeName byte[] -ArgumentList 32
$pass = "password"
$res = [Win32.NativeFunctions]::BCryptDeriveKeyPBKDF2($algo, $pass, $pass.Length, $salt, $salt.Length, 10000, $key, $key.Length, 0)
if ($res -ne 0) {
    throw "Failed to derive key"
}

[Win32.NativeFunctions]::BCryptCloseAlgorithmProvider($algo, 0)
```

Using Add-Type does have some downsides, it creates a temporary DLL file on disk and it takes more time to compile. None of these are really issues for this scenario but it has been something I wanted to work around for some time. I decided to take the opportunity to find another way around Add-Type and ultimately came across a way of calling these native functions with .NET Reflection. There are some blog posts which I have referenced at the bottom of this post, that helped me to understand how to use reflection. This resulted in the following cmdlet [Invoke-Win32Api](https://github.com/jborean93/PowerShell-AnsibleVault/blob/master/AnsibleVault/Private/Invoke-Win32Api.ps1) which can be used to call any Win32 APIs. If you are interested in learning more about this I recommend you look at the code and references to see how it works.

In the end, [New-PBKDF2Key](https://github.com/jborean93/PowerShell-AnsibleVault/blob/master/AnsibleVault/Private/New-PBKDF2Key.ps1) is what I ended up with. It calls the native Win32 APIs to produce the key required in a way that works on Windows 7/Server 2008 R2 and newer. In the future, I may add a conditional check to use Rfc2898DeriveBytes if the HashAlgorithmName constructor is available so this works on .NET Core but that wasn’t part of my original goals.

### AES in CTR mode

Now that we have solved the PBKDF2 issue we move onto the next one, getting the [AesCryptoServiceProvider](https://msdn.microsoft.com/en-us/library/system.security.cryptography.aescryptoserviceprovider.aspx) to work in CTR mode. When looking at the [CipherMode](https://msdn.microsoft.com/en-us/library/system.security.cryptography.ciphermode.aspx) enumeration values, there is no option to run in CTR mode which is going to be a problem for us.

Looking at the underlying Win32 functions I was hoping this would be a similar situation as the PBKDF2 with SHA256 but unfortunately that didn’t seem to be the case, I had to implement this mode myself. I was loath to do this and was prepared to scrap this whole idea but luckily CTR mode isn’t that complex to do. From my understanding (please don’t reference me for this), it works like this;

1.  A counter is initialised from a randomly unique nonce value, this nonce is derived as part of the key from the PBKDF2 function (last 16 bytes)
2.  The counter is then encrypted with the AES cipher in ECB mode, this AES cipher is based on the 32-byte key from the PBKDF2 function (first 32 bytes)
3.  The counter is incremented by 1
4.  The result from step 2 is the XOR’d with the plaintext or ciphertext byte by byte until there are no more bytes left in the output
5.  Steps 2-4 is repeated until all bytes in the plaintext or cipher text have been XOR’d

Taking this into practice, let’s decrypt the first 32 bytes of our example cipher text, here are the inputs from the example;

```
# First 16 bytes of our encrypted bytes
e06f2f75342298841a9ed39cd62e9208

# Next 16 bytes of our encrypted bytes
a5ca1ea04e75f79a92148ab0d17ed4e7

# The starting 16-byte counter/nonce (from the PBKDF2 function)
394f9f4a44152b33234cba44c930921b

# The 32-byte AES key used in counter transformations
fc4a21fb71bfaad6a0bbb078f0704721ccad80519fc349c3ff14268fced14203
```

When using a site like [this online AES ECB cipher](http://www.cryptogrium.com/aes-encryption-online-ecb.html) we can encrypt the current counter value with the AES 256 key to get the input to the XOR function.

[![](/assets/images/2018/05/AES-ECB-Cycle-1.png)](/assets/images/2018/05/AES-ECB-Cycle-1.png)

When xoring the output `88005c016b52f9f769e9bceeb214b27b` with the next 16 bytes in the encrypted bytes array `e06f2f75342298841a9ed39cd62e9208` we get `686f73745f70617373776f72643a2073` which is `host_password: s` in UTF-8. Now we have exhausted the XOR input, we need to increment the counter and repeat the process again.

```
# Previous counter
394f9f4a44152b33234cba44c930921b

# Next counter
394f9f4a44152b33234cba44c930921c

# AES ECB encryption output of this counter
d0ba7bd23d1094e8f760fad1a20de5d5

# Next 16 bytes of our encrypted bytes to XOR
a5ca1ea04e75f79a92148ab0d17ed4e7

# XOR result
75706572736563726574706173733132

# UTF-8 string of the XOR hex string
upersecretpass12
```

Putting the outputs together we currently have `host_password: supersecretpass12`. there are still some encrypted bytes left but the process is still the same; increment the counter, encrypt counter, XOR encrypted result with the next encrypted block. Putting this into PowerShell was relatively simple and the end result is [Invoke-AESCTRCycle](https://github.com/jborean93/PowerShell-AnsibleVault/blob/master/AnsibleVault/Private/Invoke-AESCTRCycle.ps1). Because of the nature of XOR, the encryption and decryption process is exactly the same in CTR mode.

### PKCS7 padding

So we have solved the hurdle of PBKDF2 with SHA256 and adding support for AES in CTR mode, the last remaining hurdle is adding a function to pad and unpad our bytes based on the PKCS7 algorithm. Usually padding is used to “pad” the input bytes so it fits the block size in a cipher, e.g. AES uses a block size of 16 so each input to the transformation process must also be 16-bytes. AES in CTR mode is actually a stream cipher so the input block does not need to be the same size, but in Ansible Vault, the data is still padded.

Usually this padding is done as part of the `AesCryptoServiceProvider` but because we implemented our own method and CTR mode is not a block cipher we need to manually pad or unpad the data. Luckily PKCS7 is a relatively simple algorithm and easily implement, it appends the same byte that is equal to the number of bytes to add for a complete block until the block is complete. The exception to this is if the input data is currently the size of the block, PKCS7 will still add another block with the value being the number of bytes added.

Here are some examples of padding in action for an 8-byte block size;

```
# 8 - 1 = 7, the byte with the value 07, is added 7 times
01 == 01 07 07 07 07 07 07 07

# 8 - 3 = 5, the byte with the value 05 is added 5 times
01 02 03 == 01 02 03 05 05 05 05 05

# When the input is the same as the block size, an extra block is added
01 02 03 04 05 06 07 08 == 01 02 03 04 05 06 07 08 08 08 08 08 08 08 08 08
```

I ended up with 2 cmdlets to achieve this [Add-Pkcs7Padding](https://github.com/jborean93/PowerShell-AnsibleVault/blob/master/AnsibleVault/Private/Add-Pkcs7Padding.ps1), and [Remove-Pkcs7Padding](https://github.com/jborean93/PowerShell-AnsibleVault/blob/master/AnsibleVault/Private/Remove-Pkcs7Padding.ps1).

## AnsibleVault module

Putting this all together, I present [AnsibleVault](https://github.com/jborean93/PowerShell-AnsibleVault), a PowerShell module that can encrypt and decrypt Ansible vaults on Windows. Earlier I stated that one of my goals was to have a way to easily maintain the script and just creating a module does not fully fit this. I wanted a way to automatically;

- Run sanity checks on the code
- Run unit and integration tests
- Automatically deploy the changes to the PowerShell Gallery

To achieve this, I used a combination of the following PowerShell modules;

- [PsScriptAnalyzer](https://github.com/PowerShell/PSScriptAnalyzer) – static code checker
- [Pester](https://github.com/pester/Pester) – testing and code coverage tool
- [PSDeploy](https://github.com/RamblingCookieMonster/PSDeploy) – tool used for simplifying the module deployment to PowerShell Gallery
- [Psake](https://github.com/psake/psake) – build automation tool
- [BuildHelpers](https://github.com/RamblingCookieMonster/BuildHelpers/) – helper tool for running a build in a CI environment like Appveyor

If you interested in how I put all of this together I highly recommend you read through [this](ramblingcookiemonster.github.io/PSDeploy-Inception/) blog post who is the author of some of those modules. I implemented most of the work that the blog talked through but added a few extra things like the PsScriptAnalyzer and code coverage steps which are two metrics I am interested in.

Ultimately I can test out changes to AnsibleVault and have a system that will reliably run tests and other checks on the changes automatically. My only wish would be a way to test against older PowerShell versions and not just one but that’s probably a project for another time. The other great thing about this workflow is that to deploy a new release to the PowerShell Gallery, all I need to do is create a new tag in GitHub. This will kick off a run in Appveyor which will publish the changes to the gallery.

## How to get it

Now that the module is part of the [PowerShell Gallery](https://www.powershellgallery.com/packages/AnsibleVault) it is quite simple to install, just run the [Install-Module](https://docs.microsoft.com/en-us/powershell/module/powershellget/Install-Module?view=powershell-6) module.

*Note: this will only work if you are running PowerShell v5 or have [PowerShellGet](https://github.com/powershell/powershellget) installed for older versions.*

[![](/assets/images/2018/05/Installing-with-PSGet.png)](/assets/images/2018/05/Installing-with-PSGet.png)

*You can set -Force to automatically accept prompt*

If you don’t want to install the module system wide (or you don’t have admin rights), you can install it just for the current user by setting `-Scope CurrentUser` on the install cmdlet. PowerShellGet makes managing modules such a simple thing to do and I highly recommend people [install it through the MSI](https://docs.microsoft.com/en-us/powershell/gallery/installing-psget) if they can’t upgrade PowerShell to version 5. If you wish to uninstall the module, the cmdlet `Uninstall-Module -Name AnsibleVault` can be used to remove it from the system.

If you don’t want to install PowerShellGet you can manually install it on the system by doing the following;

1.  Download the latest zip from GitHub [here](https://github.com/jborean93/PowerShell-AnsibleVault/releases/latest)
2.  Extract the zip
3.  Copy the folder `AnsibleVault` inside the zip to a path that is set in `$env:PSModulePath`, e.g. `C:\Program Files\WindowsPowerShell\Modules` or `C:\Users\<user>\Documents\WindowsPowerShell\Modules`
4.  Trust the downloaded files with `$path = (Get-Module -Name AnsibleVault -ListAvailable).ModuleBase; Unblock-File -Path $path\*.psd1; Unblock-File -Path $path\Public\*.ps1; Unblock-File -Path $path\Private\*.ps1`
5.  Restart PowerShell so the unblock policy is applied to the module

*Note: You are not limited to those paths, you can add a new entry to the environment variable `PSModulePath` if you want to use another path.*

[![](/assets/images/2018/05/AnsibleVault-Manual-Install.png)](/assets/images/2018/05/AnsibleVault-Manual-Install.png)

*Here I have installed it under the user’s profile*

## Using the AnsibleVault module

Now that the module is installed, the cmdlets `Get-DecryptedAnsibleVault` and `Get-EncryptedAnsibleVault` can be used like any other cmdlet. Here is the basic syntax for each module;

```
Get-DecryptedAnsibleVault `
    [-Value] <String> `
    [-Password] <SecureString> `
    [-Encoding <Encoding>] `
    [<CommonParameters>]

Get-DecryptedAnsibleVault `
    [-Path] <String> `
    [-Password] <SecureString> `
    [-Encoding <Encoding>] `
    [<CommonParameters>]

Get-EncryptedAnsibleVault `
    [-Value] <String> `
    [-Password] <SecureString> `
    [-Id <String>] `
    [<CommonParameters>]

Get-EncryptedAnsibleVault `
    [-Path] <String> `
    [-Password] <SecureString> `
    [-Id <String>] `
    [<CommonParameters>]
```

Here are what each parameter does;

- `Value`: A string value to encrypt/decrypt, this can also be sent as a pipeline input
- `Path`: The path to a file whose contents will be encrypted/decrypted
- `Password`: A secure string that is the password for the vault
- `Encoding`: When decrypting a vault, this is the final output string encoding of the vault (default if UTF-8). You shouldn’t have to touch this parameter but if the source vault file was not UTF-8 than this can control the final decrypted output
- `Id`: An optional parameter that specifies the ID to assign to the new vault string

You can use a combination of these cmdlets and pipelining to achieve similar results to some common `ansible-vault` commands, here are some common examples to replace existing `ansible-vault` functionality;

```
# ansible-vault encrypt C:\temp\vault.yml --ask-vault-pass
Get-EncryptedAnsibleVault -Path C:\temp\vault.yml | Set-Content -Path C:\temp\vault.yml

# ansible-vault encrypt C:\temp\vault.yml --vault-id dev@prompt
Get-EncryptedAnsibleVault -Path C:\temp\vault.yml -Id dev | Set-Content -Path C:\temp\vault.yml

# ansible-vault rekey C:\temp\vault.yml --ask-vault-pass
Get-DecryptedAnsibleVault -Path C:\temp\vault.yml | Get-EncryptedAnsibleVault | Set-Content -Path C:\temp\vault.yml

# ansible-vault view C:\temp\vault.yml --ask-vault-pass
Get-DecryptedAnsibleVault -Path C:\temp\vault.yml

# ansible-vault decrypt C:\temp\vault.yml --ask-vault-pass
Get-DecryptedAnsibleVault -Path C:\temp\vault.yml | Set-Content -Path C:\temp\vault.yml

# ansible-vault encrypt_string --stdin-name 'vault_variable'
$vault_text = Read-Host -Prompt "Enter string to encrypt" | Get-EncryptedAnsibleVault
Write-Output -InputObject "vault_variable: !vault |`n    $($vault_text.Replace("`n", "`n    "))"

# add a new variable to an existing vault file
$vault_pass = Read-Host -Prompt "Enter vault password" -AsSecureString
$vault_text = Get-DecryptedAnsibleVault -Path C:\temp\vault.yml -Password $vault_pass
$vault_text += "`nanother_host_secret: you'll never guess this"
Get-EncryptedAnsibleVault -Value $vault_text -Password $vault_pass | Set-Content -Path C:\temp\vault.yml
```

[![](/assets/images/2018/05/AnsibleVault-Example.png)](/assets/images/2018/05/AnsibleVault-Example.png)

*AnsibleVault in Action, the sky is the limit with what you can do*

# References

I would like to point out a few different blogs/sites that helped me along the way

- [PBKDF2 SHA256 C# Implementation](https://blogs.msdn.microsoft.com/dsnotes/2017/09/20/pbkdf2-net-api-does-not-exists-with-sha256-implementation-here-pbkdf2-stands-for-password-based-key-derivation-function-2/)
- [Lee Holmes and P/Invoke through .NET Reflection](http://www.leeholmes.com/blog/2007/10/02/managing-ini-files-with-powershell/)
- [The Scripting Guys – Another P/Invoke through .NET Reflection](https://blogs.technet.microsoft.com/heyscriptingguy/2013/06/27/use-powershell-to-interact-with-the-windows-api-part-3/)
- [Hans Wolff and his AES CTR implementation](https://gist.github.com/hanswolff/8809275)
- [Rambling Cookie Monster and his PSake reference](http://ramblingcookiemonster.github.io/PSDeploy-Inception/)
