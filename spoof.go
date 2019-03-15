package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"reflect"
	"regexp"

	"github.com/elazarl/goproxy"
)

var listenaddr = flag.String("addr", ":8080", "Proxy listen addr")
var rscpath = flag.String("path", "gamedata", "Path to look for game data")

type ResourceManifest struct {
	MapFile  string            `json:"mapfile"`
	Hijacked map[string]string `json:"hijackeddata"`
	UUID     string            `json:"guid"`
}

type ResourceItem struct {
	Filename string
	Size     uint32
	MD5Hash  string
}

func (a *ResourceItem) UnmarshalJSON(b []byte) error {
	var item []interface{}
	if err := json.Unmarshal(b, &item); err != nil {
		return err
	}
	if len(item) != 3 {
		return fmt.Errorf("incorrect number of entries: expecting 3, got %d", len(item))
	}
	if reflect.ValueOf(item[0]).Kind() != reflect.String {
		return fmt.Errorf("failed to parse item name %v", item[0])
	}
	if reflect.ValueOf(item[1]).Kind() != reflect.Float64 {
		return fmt.Errorf("failed to parse item size %v", item[1])
	}
	if reflect.ValueOf(item[2]).Kind() != reflect.String || len(item[2].(string)) != 32 {
		return fmt.Errorf("failed to parse item md5hash %v", item[2])
	}
	*a = ResourceItem{
		Filename: item[0].(string),
		Size:     uint32((item[1]).(float64)),
		MD5Hash:  item[2].(string),
	}
	return nil
}

func (a ResourceItem) MarshalJSON() ([]byte, error) {
	return json.Marshal([]interface{}{a.Filename, a.Size, a.MD5Hash})
}

func BuildMITMProxyHandler(rscs map[string]*ResourceManifest, proxy *goproxy.ProxyHttpServer) http.Handler {
	mapMatch := regexp.MustCompile("/web/([0-9A-Za-z]{32})/[0-9]+/Map_32.bin")
	rscMatch := regexp.MustCompile("/shareres/[0-9A-Za-z]{2}/([0-9A-Za-z]{32})")
	mapbins := make(map[string]string)
	gamersc := make(map[string]string)
	for p, manifest := range rscs {
		log.Printf("registered map.bin uuid:%s file:%s\n", manifest.UUID, filepath.Join(p, manifest.MapFile))
		mapbins[manifest.UUID] = filepath.Join(p, manifest.MapFile)
		for hash, file := range manifest.Hijacked {
			log.Printf("registered game resource md5:%s file:%s\n", hash, filepath.Join(p, file))
			gamersc[hash] = filepath.Join(p, file)
		}
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodGet {
			bURL := []byte(r.URL.Path)
			if uuid := mapMatch.FindSubmatch(bURL); uuid != nil {
				if val, ok := mapbins[string(uuid[1])]; ok {
					log.Printf("intercepted map.bin for uuid %q\n", uuid[1])
					http.ServeFile(w, r, val)
					return
				}
			}
			if md5 := rscMatch.FindSubmatch(bURL); md5 != nil {
				if val, ok := gamersc[string(md5[1])]; ok {
					log.Printf("intercepted game resource with MD5 %q\n", md5[1])
					http.ServeFile(w, r, val)
					return
				}
			}
		}
		proxy.ServeHTTP(w, r)
	})
}

func main() {
	flag.Parse()

	rscs := make(map[string]*ResourceManifest)

	filepath.Walk(*rscpath, func(path string, info os.FileInfo, err error) error {
		if err == nil {
			if !info.IsDir() && (info.Name() == "game-manifest.json") {
				// try to parse it as resource manifest file
				if b, err := ioutil.ReadFile(path); err == nil {
					var tmpManifest ResourceManifest
					if err := json.Unmarshal(b, &tmpManifest); err == nil {
						// success
						rscs[filepath.Dir(path)] = &tmpManifest
					}
				}
			}
			return nil
		} else {
			log.Printf("error walking directory: %v", err)
			return err
		}
	})

	proxy := goproxy.NewProxyHttpServer()
	spoofer := BuildMITMProxyHandler(rscs, proxy)
	// spoofer := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
	// 	if r.Method != http.MethodConnect {

	// 		// victim: cb970a9ebc1a3ed499c845b4c94497f4&version=344

	// 		if strings.Contains(r.URL.Path, "/web/4fcc10ed318a13bdb8c53a89fb5bf893/2051/Map_32.bin") {
	// 			log.Println("manifest file matched")
	// 			http.ServeFile(w, r, "gamedata/4fcc10ed318a13bdb8c53a89fb5bf893/map.bin")
	// 			return
	// 		}
	// 		if strings.Contains(r.URL.Path, "/shareres/3c/3c59ae1c3ecd60ccc9380bb503bd6d14") {
	// 			log.Println("game resource matched")
	// 			http.ServeFile(w, r, "gamedata/4fcc10ed318a13bdb8c53a89fb5bf893/data/game.bin")
	// 			return
	// 		}
	// 		// hijack the hi-quality version by default, low-quality version is Map_31.bin
	// 		// if strings.Contains(r.URL.Path, "/web/4fcc10ed318a13bdb8c53a89fb5bf893/2051/Map_32.bin") {
	// 		// 	log.Println("manifest file matched")
	// 		// 	http.ServeFile(w, r, "gamedata/4fcc10ed318a13bdb8c53a89fb5bf893/map.bin")
	// 		// 	return
	// 		// }
	// 		// if strings.Contains(r.URL.Path, "/shareres/3c/3c59ae1c3ecd60ccc9380bb503bd6d14") {
	// 		// 	log.Println("game resource matched")
	// 		// 	http.ServeFile(w, r, "gamedata/4fcc10ed318a13bdb8c53a89fb5bf893/data/game.bin")
	// 		// 	return
	// 		// }

	// 	}
	// 	proxy.ServeHTTP(w, r)
	// })

	log.Fatal(http.ListenAndServe(*listenaddr, spoofer))
}
