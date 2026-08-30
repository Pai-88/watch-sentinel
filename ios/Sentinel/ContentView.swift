import SwiftUI

struct ContentView: View {
    @State private var status = "Ready"
    @State private var diagnostics = ""
    @State private var exportURL: URL?
    @State private var busy = false
    private let exporter = HealthExporter()

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Text("Sentinel").font(.largeTitle.bold())
                Text(status).foregroundStyle(.secondary)

                Button("Export last 90 days") { Task { await runExport() } }
                    .buttonStyle(.borderedProminent)
                    .disabled(busy)

                if let url = exportURL {
                    ShareLink(item: url) {
                        Label("Share export", systemImage: "square.and.arrow.up")
                    }
                }

                if !diagnostics.isEmpty {
                    Text(diagnostics)
                        .font(.system(.footnote, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                }
            }
            .padding()
        }
    }

    private func runExport() async {
        busy = true
        defer { busy = false }
        do {
            status = "Requesting access…"
            try await exporter.requestAuthorization()

            status = "Checking what's actually there…"
            diagnostics = await exporter.diagnose(days: 90)

            status = "Fetching…"
            let records = try await exporter.fetchDailyRecords(days: 90)
            exportURL = try exporter.exportJSON(records)
            status = records.isEmpty
                ? "Exported 0 days — see below"
                : "Exported \(records.count) days"
        } catch {
            status = "Error: \(error.localizedDescription)"
        }
    }
}
