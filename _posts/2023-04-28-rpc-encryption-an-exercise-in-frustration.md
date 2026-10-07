---
layout: post
title: "RPC Encryption – An Exercise in Frustration"
date: 2023-04-28 05:58:50 +0000
permalink: /2023/04/28/rpc-encryption-an-exercise-in-frustration/
categories: []
description: "Since of the release of Windows LAPS and the introduction of encrypted passwords I’ve been working towards a way of decrypting these payloads on non-Windows platforms. One of the key components of getting this working is to not only have a working RPC client but also support the RPC authentication level RPC_C_AUTHN_LEVEL_PKT_PRIVACY. I’ve worked with …"
---

Since of the release of [Windows LAPS](https://learn.microsoft.com/en-us/windows-server/identity/laps/laps-overview) and the introduction of encrypted passwords I’ve been working towards a way of decrypting these payloads on non-Windows platforms. One of the key components of getting this working is to not only have a working RPC client but also support the RPC authentication level `RPC_C_AUTHN_LEVEL_PKT_PRIVACY`. I’ve worked with GSSAPI/SSPI before and thought this should be relatively simple, this is a tale of what is actually involved for others interested in the top. I won’t be going into too much details on the RPC process, I just wanted to focus on the authentication and subsequent message encryption details I found were not documented, or not very detailed.

# What is RPC

RPC standard for Remote Procedure Call and is a way for programs to invoke a function that lives outside of it’s process. There are many transport protocols that RPC can operator on, the [MS-RPCE](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rpce/b1470490-ce07-492a-ac7f-e2d5ce2333b4) protocol documentation even displays a nice diagram of some that are involved.

[![](/assets/images/2023/04/RPC_Transports.png)](/assets/images/2023/04/RPC_Transports.png)

In the past I’ve been able to use my SMB Python library to use RPC over SMB named pipes, known as `ncacn_np`, but another important transport protocol is RPC over TCP/IP (`ncacn_ip_tcp`). RPC over SMB can reuse the authentication and message protection features offered by the SMB protocol, but RPC over TCP needs to use the specifications defined by the RPC protocol. The specs define how authentication tokens are exchanged but it is quite a high level overview with a lot of the details down to the authentication provider used. There are two main components that need to be implemented:

- Authentication Type
- Authentication Level

# Authentication Types

The authentication level is the authentication protocol that is used to authenticate the user and provide message protection support. There are a few types/providers supported by [MS-RPCE](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rpce/d4097450-c62f-484b-872f-ddf59a7a0d36) but the ones I am focusing on are:

| Name                      | Protocol         | Value |
|---------------------------|------------------|-------|
| RPC_C_AUTHN_GSS_NEGOTIATE | Negotiate/SPNEGO | 0x09  |
| RPC_C_AUTHN_WINNT         | NTLM             | 0x0A  |
| RPC_C_AUTHN_GSS_KERBEROS  | Kerberos         | 0x10  |

The `RPC_C_AUTHN_GSS_NEGOTIATE` type will try and use `Kerberos` authentication before falling back to `NTLM`. It technically can authenticate with other protocols through the NegoEx protocol but I’m only focusing on `NTLM` and `Kerberos`. The `RPC_C_AUTHN_WINNT` and `RPC_C_AUTHN_GSS_KERBEROS` types are used when either `NTLM` or `Kerberos` are targeted explicitly outside of the `Negotiate` process. All 3 protocols follow a very basic pattern where the authentication tokens are exchanged between the client and the server with support for various authentication levels.

# Authentication Levels

An authentication level describes the level of protection the authentication type provides for the current connection. These levels are documented by [MS-RPCE](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rpce/425a7c53-c33a-4868-8e5b-2a850d40dc73) but the important one here is `RPC_C_AUTHN_LEVEL_PKT_PRIVACY (0x06)`. The level ensures that the RPC body is encrypted so that anyone capturing the network traffic will be unable to view the contents. While it is not always required to use `RPC_C_AUTHN_LEVEL_PKT_PRIVACY`, there are certain APIs that mandate this level before they can be used and it is good practice to ensure your communication is protected.

There is an extra component to the authentication level added as a Microsoft extension on `MS-RPCE`, the [PFC_SUPPORT_HEADER_SIGN flag](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rpce/4886f349-2a73-4f9e-9262-a8404462c7e9). This is a flag used to indicate to the server that the RPC header and security trailer are included in the security checksum of the payload. If this flag is not set then only the RPC body will be protected by the authentication level specified. From what I can gather, a Windows client always sets this flag but as a service it will still allow other clients to communicate without this flag. This may change in the future but essentially both modes should be supported by and client wishing to communicate with a Windows RPC service.

# RPC Payload

Before going into the details of how the authentication and encryption process is done, it is important to talk about the structure of an RPC payload. An RPC payload is split into the following segments:

| Segment              | Purpose                            |
|----------------------|------------------------------------|
| PDU Header           | Common header information          |
| Request Header       | Message type specific header data  |
| PDU Body             | Data specific to the message type  |
| Security Trailer     | Authentication info                |
| Authentication Token | The authentication token/signature |

The PDU Body is then further comprised of the following components:

| Segment                | Purpose                                |
|------------------------|----------------------------------------|
| Stub Data              | Data specific to the request operation |
| Stub Padding           | Padding data to align the stub         |
| Verification Trailer   | Additional integrity protection        |
| Authentication Padding | Padding data to align the body         |

Not all these fields are necessary for all RPC payloads but it is important to know them.

# Authentication Process

The first step of an RPC connection is to authenticate the user using the authentication type desired. This is done by sending an Bind Request and subsequent Alter Context requests until the authentication is complete. The first message is the Bind Request which can be seen in this network traffic capture.

[![](/assets/images/2023/04/RPC_Bind.png)](/assets/images/2023/04/RPC_Bind.png)

The `Auth Info` field at the bottom is the security trailer and authentication token where the security trailer states what authentication type is used and the authentication level desired. In this case the `RPC_C_AUTHN_GSS_NEGOTIATE` type and `RPC_C_AUTHN_LEVEL_PKT_PRIVACY` level are set which indicates the authentication tokens are for the Negotiate protocol and encryption will be used. Following straight after the security trailer is the authentication token, which for a bind request is the actual Kerberos/NTLM token generated from SSPI/GSSAPI.

This token can be generated on SSPI through the [InitializeSecurityContext](https://learn.microsoft.com/en-us/windows/win32/secauthn/initializesecuritycontext--negotiate) API or on GSSAPI with the [gss_init_sec_context](https://datatracker.ietf.org/doc/html/rfc2744.html#section-5.19) API. It is important to provide the SSPI flag `ISC_REQ_USE_DCE_STYLE` or GSSAPI flag `GSS_C_DCE_STYLE` when stepping through these functions as it is used to produce DCE/RPC style tokens. This is not an exhaustive list but from observation I found the DCE flag does some of the following:

- For Kerberos the exchange includes a third token will produce a third authentication token rather than the typical two
- For Negotiate the exchange will also include the `mechListMIC` value inside the SPNEGO envelope
- For NTLM no changes were observed

Another key note here is that the RPC flags set the `PFC_SUPPORT_HEADER_SIGN (0x03)` bit in the flags if the client can do integrity protection on the PDU header and security trailer. This is shown in the above exchange where `Cancel Pending` (uses the same bit value) is set in the dissected output. This flag will continue to be set in both the bind request and subsequent alter context messages until the security context is complete.

The MS-RPCE extension also document an extension PDU called [rpc_auth_3](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-rpce/a6b7b03c-4ac5-4c25-8c52-f2bec872ac97) which is meant to be used instead of an alter context payload if the client is sending the last authentication token and doesn’t expect a reply back. In testing this PDU does not seem to be necessary as the alter context PDU works in the very scenario MS-RPCE described for `rpc_auth_3`.

# Message Protection

Once the authentication process is complete, the client can now send requests to the RPC service. As the authentication level `RPC_C_AUTHN_LEVEL_PKT_PRIVACY` was configured in the authentication stage, the PDU body data will need to be encrypted. Before the data can be encrypted the RPC PDU should be built as normal, more specifically:

- The PDU body that is being encrypted should be padded to ensure it aligns with the authentication message block size
- The PDU header fragment length should be set to be the final payload size, including the authentication token at the end
- The PDU auth length should be set to the expected authentication token/signature size

The [QueryContextAttributes](https://learn.microsoft.com/en-us/windows/win32/secauthn/querycontextattributes--general) with `SECPKG_ATTR_SIZES` should provide the authentication token/signature length through the returned `cbSecurityTrailer` field. On GSSAPI the [gss_wrap_iov_length](https://web.mit.edu/kerberos/krb5-latest/doc/appdev/gssapi.html#iov-message-wrapping) API can be used to return the expected authentication token/signature size.

Once the plaintext PDU has been generated it is time to encrypt the data. On SSPI encryption is done using the [EncryptMessage](https://learn.microsoft.com/en-us/windows/win32/api/sspi/nf-sspi-encryptmessage) API and on GSSAPI it’s with the [gss_wrap_iov](https://web.mit.edu/kerberos/krb5-latest/doc/appdev/gssapi.html#iov-message-wrapping) API. Both of these functions take in an array of buffers and use that to wrap the data.

As the documentation for this was not clear at all I ended up tracing the SSPI calls using [PSDetour](https://github.com/jborean93/PSDetour) and was able to see the following during a real RPC exchange:

```
EncryptMessage(Context: 0x1E752D17F28, Qop: 0, Message: 0xC8EED8D878, SeqNo: 2)
        EncryptMessage Message(Version: 0, Buffers: 5)
                [1] Type: SECBUFFER_DATA | SECBUFFER_READONLY_WITH_CHECKSUM (1), Length: 24, Data: 05000003100000004C014C0008000000D800000001000000
                [2] Type: SECBUFFER_DATA (1), Length: 224, Data: 6C0000...
                [3] Type: SECBUFFER_DATA | SECBUFFER_READONLY_WITH_CHECKSUM (1), Length: 8, Data: 0906080000000000
                [4] Type: SECBUFFER_TOKEN (2), Length: 76, Data: 0000...
                [5] Type: SECBUFFER_PKG_PARAMS | SECBUFFER_READONLY (3), Length: 12, Data: 020000000000000000EBBFE8
EncryptMessage -> Res: 0x00000000
        EncryptMessage Message(Version: 0, Buffers: 5)
                [1] Type: SECBUFFER_DATA | SECBUFFER_READONLY_WITH_CHECKSUM (1), Length: 24, Data: 05000003100000004C014C0008000000D800000001000000
                [2] Type: SECBUFFER_DATA (1), Length: 224, Data: E428...
                [3] Type: SECBUFFER_DATA | SECBUFFER_READONLY_WITH_CHECKSUM (1), Length: 8, Data: 0906080000000000
                [4] Type: SECBUFFER_TOKEN (2), Length: 76, Data: 0504...
                [5] Type: SECBUFFER_PKG_PARAMS | SECBUFFER_READONLY (3), Length: 12, Data: 020000000000000000EBBFE8
```

In summary the RPC client on Windows provides 5 buffers to the `EncryptMessage` function:

- \[1\] – The PDU header + request header data is marked as `SECBUFFER_READONLY_WITH_CHECKSUM`
- \[2\] – The PDU body (including the verification trailer and padding)
- \[3\] – The Security trailer is marked as `SECBUFFER_READONLY_WITH_CHECKSUM`
- \[4\] – An output buffer that will store the signature generated from the first 3 buffers
- \[5\] – Extra metadata about the payload marked as `SECBUFFER_PKG_PARAMS`

The data in the 2nd buffer will be encrypted in place and the 3rd buffer will contain the generated signature. With the resulting information it is possible to now replace the PDU body with the encrypted output from `EncryptMessage` and include the signature generated as the RPC authentication token value.

It was trickier to figure out the buffer types needed when `PFC_SUPPORT_HEADER_SIGN` was not used as the Windows client always set this flag, but in the end I was able to get a trace on the server as it responded to a client that didn’t set these flags. This is what the `EncryptMessage` trace looked like

```
EncryptMessage(Context: 0x1AA7EBF95F8, Qop: 0, Message: 0x842F47F5C0, SeqNo: 1)
    EncryptMessage Message(Version: 0, Buffers: 5)
        [1] Type: SECBUFFER_DATA | SECBUFFER_READONLY (1), Length: 24, Data: 0500020310000000B0031000010000007403000001000000
        [2] Type: SECBUFFER_DATA (1), Length: 896, Data: 5603...
        [3] Type: SECBUFFER_DATA | SECBUFFER_READONLY (1), Length: 8, Data: 09060C0000000000
        [4] Type: SECBUFFER_TOKEN (2), Length: 16, Data: 0000000000000000C0E40A75FC7F0000
        [5] Type: SECBUFFER_PKG_PARAMS | SECBUFFER_READONLY (3), Length: 12, Data: 01000000030000000273FFFC
EncryptMessage -> Res: 0x00000000
    EncryptMessage Message(Version: 0, Buffers: 5)
        [1] Type: SECBUFFER_DATA | SECBUFFER_READONLY (1), Length: 24, Data: 0500020310000000B0031000010000007403000001000000
        [2] Type: SECBUFFER_DATA (1), Length: 896, Data: 193B...
        [3] Type: SECBUFFER_DATA | SECBUFFER_READONLY (1), Length: 8, Data: 09060C0000000000
        [4] Type: SECBUFFER_TOKEN (2), Length: 16, Data: 01000000500B6FDD07DA479100000000
        [4] Type: SECBUFFER_PKG_PARAMS | SECBUFFER_READONLY (3), Length: 12, Data: 01000000030000000273FFFC
```

The buffers are essentially the same as before except now buffer 1 and 3 have the flag `SECBUFFER_READONLY` and not `SECBUFFER_READONLY_WITH_CHECKSUM`. NTLM doesn’t seem to differentiate between these flags which means `PFC_SUPPORT_HEADER_SIGN` doesn’t add any protection for NTLM but for Kerberos it does adjust how the signature is calculated.

Now that I am know what Windows is doing I was then able to figure out what the equivalent buffer types were for GSSAPI. Here is what I’ve mapped out

| SSPI                             | GSSAPI                        |
|----------------------------------|-------------------------------|
| SECBUFFER_DATA                   | GSS_IOV_BUFFER_TYPE_DATA      |
| SECBUFFER_TOKEN                  | GSS_IOV_BUFFER_TYPE_HEADER    |
| SECBUFFER_READONLY_WITH_CHECKSUM | GSS_IOV_BUFFER_TYPE_SIGN_ONLY |
| SECBUFFER_READONLY               | GSS_IOV_BUFFER_TYPE_EMPTY     |

Unlike SSPI the GSSAPI buffer type `GSS_IOV_BUFFER_TYPE_SIGN_ONLY` is not a flag attribute but an actual type. From testing it acts like the equivalent of `SECBUFFER_DATA | SECBUFFER_READONLY_WITH_CHECKSUM`. The `SECBUFFER_DATA | SECBUFFER_READONLY` combination does not have a direct equivalent in GSSAPI but by using `GSS_IOV_BUFFER_TYPE_EMPTY`, the wrapping function will effectively ignore those fields like SSPI does.

Putting this together these are the buffer used for an encryption step when `PFC_SUPPORT_HEADER_SIGN` is negotiated:

| Buffer Idx | SSPI | GSSAPI | Data |
|----|----|----|----|
| 1 | SECBUFFER_DATA \| SECBUFFER_READONLY_WITH_CHECKSUM | GSS_IOV_BUFFER_TYPE_SIGN_ONLY | The PDU header up to the body |
| 2 | SECBUFFER_DATA | GSS_IOV_BUFFER_TYPE_DATA | The PDU body |
| 3 | SECBUFFER_DATA \| SECBUFFER_READONLY_WITH_CHECKSUM | GSS_IOV_BUFFER_TYPE_SIGN_ONLY | The security trailer |
| 4 | SECBUFFER_TOKEN | GSS_IOV_BUFFER_TYPE_HEADER | Empty, signature will be allocated here |

These are the buffers used when `PFC_SUPPORT_HEADER_SIGN` was not negotiated:

| Buffer Idx | SSPI | GSSAPI | Data |
|----|----|----|----|
| 1 | SECBUFFER_DATA \| SECBUFFER_READONLY | GSS_IOV_BUFFER_TYPE_EMPTY | The PDU header up to the body |
| 2 | SECBUFFER_DATA | GSS_IOV_BUFFER_TYPE_DATA | The PDU body |
| 3 | SECBUFFER_DATA \| SECBUFFER_READONLY | GSS_IOV_BUFFER_TYPE_EMPTY | The security trailer |
| 4 | SECBUFFER_TOKEN | GSS_IOV_BUFFER_TYPE_HEADER | Empty, signature will be allocated here |

It is also possible to just not include buffer 1 and 3 for GSSAPI, but it is important to keep them present for NTLM support on SSPI as it uses those values to generate the signature.

The decryption process uses the identical buffers on the [DecryptMessage](https://learn.microsoft.com/en-us/windows/win32/api/sspi/nf-sspi-decryptmessage) and [gss_unwrap_iov](https://web.mit.edu/kerberos/krb5-latest/doc/appdev/gssapi.html#iov-message-wrapping) APIs. The only difference is that the final buffer will contain the signature from the response for it to validate.

This may not be correct for all authentication protocols available but this combination works for both Kerberos and NTLM.

There are more scenarios, like fragmentation and integrity only protection, I have not considered during my investigation so the details in this post may not be 100% correct. Hopefully it’s enough to help you on your RPC client implementation if you ever go down this deep and dark road. I was able to use this information and package it up into my Python authentication library [pyspnego](https://github.com/jborean93/pyspnego). The RPC/DCE components was just added with [this PR](https://github.com/jborean93/pyspnego/pull/63) and should be available in the upcoming release.
