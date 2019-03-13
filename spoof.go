package main

import (
	"flag"
	"log"
	"net/http"
	"strings"

	"github.com/elazarl/goproxy"
)

var listenaddr = flag.String("addr", ":8080", "Proxy listen addr")

func main() {
	flag.Parse()
	proxy := goproxy.NewProxyHttpServer()
	spoofer := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodConnect {
			if strings.Contains(r.URL.Path, "/web/4fcc10ed318a13bdb8c53a89fb5bf893/2051/Map_32.bin") {
				http.ServeFile(w, r, "qfzct.bin")
				return
			}
		}
		proxy.ServeHTTP(w, r)
	})

	log.Fatal(http.ListenAndServe(*listenaddr, spoofer))
}
