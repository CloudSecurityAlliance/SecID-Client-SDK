# SecID Go client

Go client for the [SecID](https://github.com/CloudSecurityAlliance/SecID)
resolve API. Standard library only, no dependencies.

The module lives in the `go/` subdirectory of this repository, so its module
path is `github.com/CloudSecurityAlliance/SecID-Client-SDK/go` and the package
name is `secid`.

## Library

```bash
go get github.com/CloudSecurityAlliance/SecID-Client-SDK/go
```

```go
import secid "github.com/CloudSecurityAlliance/SecID-Client-SDK/go"

client := secid.NewClient("") // "" = the public resolver
resp, err := client.Resolve("secid:advisory/mitre.org/cve#CVE-2021-44228")
if err != nil {
	// transport or parse failure (timeout, oversized body, non-JSON body)
}
fmt.Println(resp.Status, resp.BestURL())
```

`Resolve` returns `(nil, error)` for transport and parse failures and
`(*Response, nil)` for anything the server answered, including
`Status == "error"`. `BestURL` returns only absolute `http`/`https` URLs.

## CLI

```bash
go install github.com/CloudSecurityAlliance/SecID-Client-SDK/go/cmd/secid@latest
secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
secid --json "secid:advisory/mitre.org/cve#CVE-2021-44228"
```

From a checkout, without installing:

```bash
cd go && go run ./cmd/secid "secid:advisory/mitre.org/cve#CVE-2021-44228"
```

## Copying instead of importing

`secid.go` is a single self-contained file. Copy it into your own package and
change the `package secid` line to your package name.

## Versions

Because the module is in a subdirectory, its release tags carry the
subdirectory prefix: `go/v1.0.0`, not `v1.0.0`. A bare `v1.0.0` tag on this
repository is invisible to `go get`. See [PUBLISHING.md](../PUBLISHING.md).

## Tests

```bash
cd go && go test -v ./...
```
