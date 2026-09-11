#!/usr/bin/env bash
# Sourced by setup.sh (not executed directly). Sets:
#   GUM         - path to a usable gum binary, or "" if unavailable
#   GUM_TMP_DIR - the throwaway dir gum was downloaded into, or "" if we
#                 used an existing system install (nothing to clean up)
# Never installs gum system-wide - a temp download is the only "install"
# this does, and the caller is expected to rm -rf GUM_TMP_DIR on exit.
GUM=""
GUM_TMP_DIR=""

if command -v gum >/dev/null 2>&1; then
  GUM="$(command -v gum)"
else
  _gum_os="$(uname -s)"
  _gum_arch_raw="$(uname -m)"
  case "$_gum_arch_raw" in
    x86_64) _gum_arch=x86_64 ;;
    aarch64|arm64) _gum_arch=arm64 ;;
    *) _gum_arch="" ;;
  esac

  if [ -n "$_gum_arch" ] \
    && { [ "$_gum_os" = "Linux" ] || [ "$_gum_os" = "Darwin" ]; } \
    && command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1; then
    _gum_tag="$(curl -fsSL https://api.github.com/repos/charmbracelet/gum/releases/latest 2>/dev/null \
      | grep -oE '"tag_name": *"[^"]+"' | head -1 | cut -d'"' -f4)"
    if [ -n "$_gum_tag" ]; then
      _gum_version="${_gum_tag#v}"
      _gum_url="https://github.com/charmbracelet/gum/releases/download/${_gum_tag}/gum_${_gum_version}_${_gum_os}_${_gum_arch}.tar.gz"
      _gum_tmp="$(mktemp -d)"
      if curl -fsSL "$_gum_url" -o "$_gum_tmp/gum.tar.gz" 2>/dev/null \
        && tar -xzf "$_gum_tmp/gum.tar.gz" -C "$_gum_tmp" 2>/dev/null; then
        _gum_bin="$(find "$_gum_tmp" -maxdepth 2 -name gum -type f | head -1)"
        if [ -n "$_gum_bin" ]; then
          chmod +x "$_gum_bin"
          GUM="$_gum_bin"
          GUM_TMP_DIR="$_gum_tmp"
        fi
      fi
      [ -n "$GUM" ] || rm -rf "$_gum_tmp"
    fi
  fi

  unset _gum_os _gum_arch_raw _gum_arch _gum_tag _gum_version _gum_url _gum_tmp _gum_bin
fi
