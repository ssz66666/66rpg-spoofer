# 66rpg-spoofer

欺骗橙光app下载任意游戏文件

## 要求

需求 golang 1.11+

旧版本golang需运行
```
go get github.com/elazarl/goproxy
```

## 用法

### 下载源码

```
git clone http://github.com/ssz66666/66rpg-spoofer
```
如果你使用的是不支持go module的老版本golang，请先运行
```
go get github.com/elazarl/goproxy
```
获取依赖。

### 设置欺骗的文件

待更新……

### 运行本地代理


运行工具：

```
go run spoof.go [-addr=[{addr地址}]:{port端口}]
```

例如：
```
go run spoof.go -addr=:8080
```

注意可能需要临时调整防火墙设置。

### 下载游戏

在手机上设置HTTP代理为你电脑的内网ip地址+端口
打开橙光app，前往你设置好的游戏页面下载。

完成后改回代理设置。