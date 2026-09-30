// generate.go — a code generator. It reads a template off disk and writes a
// file. There is no account, no row and no database, which is why this
// fixture's declaration is an honest zero and why one account-scoped statement
// dropped in here is a failure rather than a curiosity.

package generate

import (
	"os"
	"strings"
)

// Render writes the named template with the named values substituted.
func Render(templatePath string, values map[string]string) (string, error) {
	raw, err := os.ReadFile(templatePath)
	if err != nil {
		return "", err
	}
	out := string(raw)
	for key, value := range values {
		out = strings.ReplaceAll(out, "{{"+key+"}}", value)
	}
	return out, nil
}
