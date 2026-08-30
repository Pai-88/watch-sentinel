import SwiftUI

struct ContentView: View {
    @State private var status = "Ready"
    @State private var exportURL: URL?
    private let exporter = HealthExporter()

    var body: some View {
        VStack(spacing: 24) {
            Text("Sentinel").font(.largeTitle.bold())
            Text(status).foregroundStyle(.secondary)

            Button("Export last 90 days") {
                Task {
                    do {
                        status = "Requesting access…"
                        try await exporter.requestAuthorization()
                        status = "Fetching…"
                        let records = try await exporter.fetchDailyRecords(days: 90)
                        exportURL = try exporter.exportJSON(records)
                        status = "Exported \(records.count) days"
                    } catch {
                        status = "Error: \(error.localizedDescription)"
                    }
                }
            }
            .buttonStyle(.borderedProminent)

            if let url = exportURL {
                ShareLink(item: url) { Label("Share export", systemImage: "square.and.arrow.up") }
            }
        }
        .padding()
    }
}
