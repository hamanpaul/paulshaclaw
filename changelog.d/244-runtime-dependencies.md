### Fixed
- operator shell 現在直接宣告 PyYAML 與 Textual runtime dependencies（#244）；fresh editable install 不再依賴外部 plane 的 transitive dependency 或 CI 額外 stage requirements 才能啟動 cost 與 cockpit。
