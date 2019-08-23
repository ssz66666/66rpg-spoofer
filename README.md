# 66rpg-spoofer

利用中间人攻击欺骗橙光app下载任意游戏文件

## 要求

需求 golang 1.11+

旧版本golang需运行
```
go get github.com/elazarl/goproxy
```
运行配置脚本需 python 3.7+

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

下列步骤需要本地已配置好python 3.7+

1. 首先准备被替换掉的已上架游戏的uuid，可以用下面的脚本：

    ```
    > python orange.py info 橙光游戏数字ID
    该游戏的uuid 该游戏的最新版本
    ```

    以[《潜伏之赤途》](http://www.66rpg.com/game/uncheck/2992)作示例（数字ID为2992）：

    ```
    python orange.py info 2992          # 潜伏之赤途
    4fcc10ed318a13bdb8c53a89fb5bf893 2056 # 返回值前为uuid，后为最新版本 
    ```

2. 生成对应本地橙光游戏的元数据并将资源复制至`66rpg-spoofer所在目录/gamedata/任意目录`下：

    ```
    > python orange.py manifest --uuid 被替换游戏的uuid --local-path 本地游戏/工程目录 --pack-sideloader 输出目录
    ```

    例如将《潜伏之赤途》替换为位于`C:\Users\test\Documents\AvgMakerOrange\我的作品1\`的本地游戏文件，  
    目标文件夹位于`C:\Users\test\Documents\66rpg-spoofer\gamedata\mygame\`：

    ```
    > python orange.py manifest --uuid 4fcc10ed318a13bdb8c53a89fb5bf893           \
        --local-path "C:\Users\test\Documents\AvgMakerOrange\我的作品1\"           \
        --pack-sideloader "C:\Users\test\Documents\66rpg-spoofer\gamedata\mygame\"
    ```

### 运行本地代理


运行工具：

```
go run spoof.go [-addr=[{addr地址}]:{port端口}] [-path={资源目录，默认为当前目录下gamedata文件夹}]
```

例如：
```
go run spoof.go -addr=:8080 -path="/path/to/game/resources"
```

注意可能需要临时调整防火墙设置。

### 下载游戏

在手机上设置HTTP代理为你电脑的内网ip地址+端口
打开橙光app，前往你设置好的游戏页面下载。

完成后改回代理设置。