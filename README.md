# ddns-IPv6

### 通过部署私有DNS服务器实现IPv6的DDNS服务

你只需要具有一台公网地址的服务器以及一个解析了`NS`记录的域名即可实现全自动化IPv6公网地址域名解析  
This function enables the implementation of IPv6 DDNS (Dynamic Domain Name System) services through the deployment of a private DNS server.  
All you need is a server with a public network address and a domain name that has resolved NS (Name Server) records. This setup allows for fully automated domain name resolution of IPv6 public network addresses. It’s a convenient and efficient way to manage your network infrastructure and devices.  
For example, you can use it combine the domain name to your dynamic ipv6 address about your Windows pc, and then active it to pro version and turn on then remote control function, so you can use your computer with RDP via ipv6 which bind in your domain name
> ## Example  
> 1、具有域名`example.com`，在域名运营商处解析一个`NS`记录`devices.example.com`到你的服务器上  
> (一般的,`NS`记录要求解析值为一个域名，此时可以先解析一个`A记录`到目标服务器，然后把`NS记录`值填写为`A记录`的域名)  
> 2、将本项目使用克隆到你的设备，在服务器上放置`server.py`及其配置`config.server.yaml`，在需要解析的主机上放置`client.py`和配置文件`config.client.yaml`  
> 3、安装python后，使用 `pip install -r requirements.txt`安装所需依赖项，然后分别在服务器和客户端使用python运行文件
> 
### 配置文件说明
1、配置文件分为服务器配置和客户端配置，它们由不同的脚本进行解析，内部数据具有一定关联性  
2、服务器配置文件：
```yaml
listening:  # ------------------------> 监听地址和端口配置
  http_api:  # ------------> http api的地址和端口，可配合nginx进行转发
    host: 0.0.0.0
    port: 3210
  dns:  # -----------------> dns服务器配置
    udp:  # --------> udp监听地址和端口
      host: 0.0.0.0
      port: 53
    tcp: # ---------> tcp监听地址和端口
      host: 0.0.0.0
      port: 53

addresses: # --------------------------> 可用解析域名列表，客户端发来的域名必须在这个列表中
  - a.us.gov
  - b.us.gov

secret: 123123xxx  # ------------------> 校验签名密钥，和客户端必须保持一致，否则认证不能通过

record:  # ----------------------------> DNS记录配置
  expire_time_seconds: 600  # ----> 最低超时时间，在这个时间内客户端必须发起请求，否则会被清除记录，类似于TTL，但是是服务器强制的一个最小ttl，尽管客户端发来ttl比这个大，超过这个时间依然会被清理
  poll_period_seconds: 60   # ----> 记录超时轮询周期
  
functions:   # ------------------------> 功能开关
  log:   # ------------------------> 日志记录设置
    write_log_file: True  # ---> 是否将日志输出到文件以便调试和追踪问题

```
3、客户端配置文件：
```yaml
info:  # ---------------------------------------> 客户端信息
  name: a.us.gov   # ------------------> 客户端域名，必须要在服务器规定的列表当中
  ttl_seconds: 30  # ------------------> 客户端自定义TTL，可以很大，但是依然遵循服务端定义的超时清除策略

server_config:  # ------------------------------> 服务端信息
  secret: 123123xxx  # ----------------> 校验签名密钥，和服务端必须保持一致，否则认证不能通过
  api: http://127.0.0.1:3210  # -------> 服务端的更新记录接口，不一定要和服务器保持一致，能够配置nginx代理，数据可以抵达服务器进程的端口即可

time_policy:  # --------------------------------> 客户端时间策略
  scan_time_seconds: 10  # -----------> 多久检测一次本机IPv6是否发生变化
  min_report_time_seconds: 500  # ----> 最少多少时间上报一次，即使不发生更新也上报，保证数据最新，以免服务器丢弃

functions:   # ------------------------> 功能开关
  log:   # ------------------------> 日志记录设置
    write_log_file: True  # ---> 是否将日志输出到文件以便调试和追踪问题
```
**注意**
> 一般来说，时间关系应该为：  
> 服务器强制超时时间>客户端自定义TTL>客户端强制提交时间>客户端检测变化时间  

<h1 style="color: #f00;">FUCK CSDN</h1> 
声明：为了维护清朗网络环境，抵制国内抄袭、搬运风气，<span style="color: #f00; font-size: 1.3em; font-weight: bolder;">不得以任何形式搬运本人的任何项目到毒瘤网站CSDN（csdn.net及其所属其它网站、平台）</span><br>
转载其余社区请注明本项目地址，维护干净的互联网环境，也有您的一份功劳