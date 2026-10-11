# Gemma Find

An Omarchy bar plugin that searches folders you choose by meaning. EmbeddingGemma 2 ranks text and images on this machine. Gemma 4 E2B can write a short answer from those matches. Both models run through LiteRT-LM in a helper process. The Quickshell plugin does not load the models itself.

Search still returns files when Gemma 4 is not installed. Ask shows those matches too, and adds an answer when Gemma 4 is installed. Nothing is downloaded or indexed when the plugin loads. Opening the overlay only reads status. Download and Index run only from the overlay buttons or the terminal commands below.

Audio and video are not indexed.

## Install

Copy the checkout into a new plugin directory, then validate and enable it. Validate before creating `runtime/`: that folder contains symlinks, and `omarchy plugin validate` rejects any symlink in the plugin tree.

```sh
/usr/bin/python3 -I -S -c 'import pathlib, shutil; source = pathlib.Path.home()/"Development/oma-gemma-find"; target = pathlib.Path.home()/".config/omarchy/plugins/io.github.cfaulkingham.oma-gemma-find"; shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "runtime"))'
omarchy plugin validate "$HOME/.config/omarchy/plugins/io.github.cfaulkingham.oma-gemma-find"
omarchy-shell shell rescanPlugins
omarchy plugin enable io.github.cfaulkingham.oma-gemma-find --section right
```

The bar button toggles the overlay. From a terminal:

```sh
omarchy-shell shell toggle io.github.cfaulkingham.oma-gemma-find
```

## Setup

The helper needs Python 3.14 and the pinned `litert-lm-api` 0.18.0 wheel. From the installed plugin directory, after validation:

```sh
bin/setup-runtime
```

That command looks for `uv` under the passwd home at `.local/bin/uv`, then at `/usr/bin/uv`. It creates `runtime/` next to the plugin and installs the wheel named in `requirements.txt` with hash checking. It does not install anything else. Opening the plugin does not run it.

Then download the two pinned model files (about 370 MiB and about 2.4 GiB):

```sh
bin/oma-gemma-find fetch
```

The Download button in the overlay does the same thing. The files are:

| Model | Size | sha256 |
| --- | --- | --- |
| EmbeddingGemma 2 text-vision 440M | 387710976 | `92dcbea108899e5d6e30d919b0744f90d9967e80c67a4ab5503ac16d54f62eb0` |
| Gemma 4 E2B | 2588147712 | `181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c` |

They are fetched from:

- `https://huggingface.co/litert-community/embeddinggemma-2-text-vision-440m-litert-lm/resolve/main/embeddinggemma-2-text-vision-440m.litertlm`
- `https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm`

Redirects are followed only when the next URL is HTTPS on `huggingface.co` or a host ending in `.hf.co`. The download sends no account token and does not use a proxy. A file is kept only when its size and sha256 match the table. The status line treats a model as present when that filename is a regular file of the pinned size. Search and Ask hash the file again before loading it.

## Using it

Type an absolute folder path and click Add. The folder must already exist and must not be a symlink. Relative paths and `..` are refused. Then click Index.

Enter or Search ranks files. Ctrl+Enter or Ask sends the top matches to Gemma 4, which is started with tools disabled and no automatic tool calling. The answer is shown as plain text and is not executed. Click a result to open that file with `/usr/bin/xdg-open`. Only paths under a folder you added can be opened.

Closing the overlay keeps the last results until the next search or answer, or until the shell exits. Escape cancels a running helper, and otherwise closes the overlay.

The index reads text and code (markdown, plain text, and common source extensions) plus PNG, JPEG, and WebP images, checked by file header. It skips symlinks, dot names, and directories such as `.git`, `node_modules`, and `runtime`. The default backend is CPU. The overlay does not change that setting.

## What is stored

- `~/.local/state/oma-gemma-find/config.json` holds the folder list.
- `~/.local/state/oma-gemma-find/index.sqlite` holds paths, excerpts, and embeddings.
- `~/.local/share/oma-gemma-find/models/` holds the two model files.

The home directory used for those paths comes from the passwd entry, not from an overlay setting. The overlay cannot point the helper at a different state directory.

## Privacy

Indexing and search stay on this machine. The only network use is the explicit model download to the Hugging Face URLs above. Folder contents are not uploaded. Gemma 4 sees only the question and up to four retrieved passages, and it is instructed to ignore instructions inside those passages. Model text is displayed as plain text.

## Tests

From the project directory:

```sh
/usr/bin/python3 -B -m unittest discover -s tests -v
node tests/test_ui.cjs
omarchy plugin validate "$PWD"
```

The unit tests use stand-ins for LiteRT. They do not download models or create `runtime/`.

## Removal

```sh
omarchy plugin remove io.github.cfaulkingham.oma-gemma-find
```

Omarchy removes the installed plugin directory, including a `runtime/` created inside that install. These directories are kept:

- `~/.local/state/oma-gemma-find`
- `~/.local/share/oma-gemma-find`

They hold the index and the downloaded models. A source checkout, such as `~/Development/oma-gemma-find/`, is also left in place. No keyring entry, user service, sudoers rule, or keybinding is installed.

## References

- https://developers.google.com/edge/litert
- https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/
- https://huggingface.co/litert-community/embeddinggemma-2-text-vision-440m-litert-lm
- https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm

MIT licensed. This is an independent plugin, not a Google product. EmbeddingGemma and Gemma are used under their model licenses.
