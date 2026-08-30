import HealthKit
import Foundation

/// Reads the daily physiological metrics we need for illness early-warning
/// and serialises them to JSON for export to the Mac pipeline.
///
/// Metrics chosen because they are the ones shown (Stanford/Whoop studies)
/// to deviate 1-3 days BEFORE symptom onset:
///  - resting heart rate (rises)
///  - HRV / SDNN (falls)
///  - respiratory rate during sleep (rises)
///  - wrist temperature deviation (rises)
final class HealthExporter {
    private let store = HKHealthStore()

    private let types: [HKQuantityTypeIdentifier] = [
        .restingHeartRate,
        .heartRateVariabilitySDNN,
        .respiratoryRate,
        .appleSleepingWristTemperature,
    ]

    enum ExportError: LocalizedError {
        case healthDataUnavailable

        var errorDescription: String? {
            switch self {
            case .healthDataUnavailable:
                return "HealthKit is not available on this device."
            }
        }
    }

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw ExportError.healthDataUnavailable
        }
        let read = Set(types.compactMap { HKQuantityType.quantityType(forIdentifier: $0) })
        try await store.requestAuthorization(toShare: [], read: read)
    }

    /// Per-metric raw sample counts and date ranges.
    ///
    /// HealthKit deliberately refuses to say whether READ access was granted:
    /// a denied type returns an empty result set, exactly like a type you have
    /// permission for but no data in. So an empty export is ambiguous on its
    /// own, and this is the only way to tell the two apart — if every metric
    /// reads zero the cause is almost certainly permissions, whereas a mix of
    /// zero and non-zero means the data really is missing.
    func diagnose(days: Int = 90) async -> String {
        guard HKHealthStore.isHealthDataAvailable() else {
            return "HealthKit unavailable on this device."
        }
        let cal = Calendar.current
        let end = Date()
        let start = cal.date(byAdding: .day, value: -days, to: cal.startOfDay(for: end))!
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"

        var lines: [String] = ["Window: \(fmt.string(from: start)) → \(fmt.string(from: end))"]
        var total = 0

        for id in types {
            guard let qt = HKQuantityType.quantityType(forIdentifier: id) else {
                lines.append("• \(Self.label(id)): type unavailable on this OS")
                continue
            }
            // Write-permission status. This says nothing about read access —
            // included only because "notDetermined" proves the prompt was
            // never answered at all.
            let auth: String
            switch store.authorizationStatus(for: qt) {
            case .notDetermined: auth = "not asked"
            case .sharingDenied: auth = "write denied"
            case .sharingAuthorized: auth = "write ok"
            @unknown default: auth = "?"
            }

            do {
                let samples = try await self.samples(for: qt, from: start, to: end)
                total += samples.count
                if let first = samples.first, let last = samples.last {
                    lines.append("• \(Self.label(id)): \(samples.count) samples, "
                                 + "\(fmt.string(from: first.startDate)) → \(fmt.string(from: last.startDate))")
                } else {
                    lines.append("• \(Self.label(id)): 0 samples [\(auth)]")
                }
            } catch {
                lines.append("• \(Self.label(id)): error — \(error.localizedDescription)")
            }
        }

        if total == 0 {
            lines.append("")
            lines.append("Every metric is empty. Read access was probably denied.")
            lines.append("Fix in: Settings → Privacy & Security → Health → Sentinel,")
            lines.append("and switch all four categories on.")
        }
        return lines.joined(separator: "\n")
    }

    private func samples(for type: HKQuantityType, from start: Date,
                         to end: Date) async throws -> [HKSample] {
        try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(
                sampleType: type,
                predicate: HKQuery.predicateForSamples(withStart: start, end: end),
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierStartDate,
                                                   ascending: true)]) { _, samples, error in
                if let error { cont.resume(throwing: error) }
                else { cont.resume(returning: samples ?? []) }
            }
            store.execute(q)
        }
    }

    private static func label(_ id: HKQuantityTypeIdentifier) -> String {
        switch id {
        case .restingHeartRate: return "Resting HR"
        case .heartRateVariabilitySDNN: return "HRV SDNN"
        case .respiratoryRate: return "Respiratory rate"
        case .appleSleepingWristTemperature: return "Wrist temp"
        default: return id.rawValue
        }
    }

    struct DailyRecord: Codable {
        let date: String            // "2026-08-30"
        var metrics: [String: Double] = [:]
    }

    /// Fetch daily averages for the last `days` days for every metric.
    func fetchDailyRecords(days: Int = 90) async throws -> [DailyRecord] {
        let cal = Calendar.current
        let end = cal.startOfDay(for: Date())
        let start = cal.date(byAdding: .day, value: -days, to: end)!
        var records: [String: DailyRecord] = [:]
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"

        for id in types {
            guard let qt = HKQuantityType.quantityType(forIdentifier: id) else { continue }
            let stats = try await dailyAverages(for: qt, from: start, to: end, calendar: cal)
            for (day, value) in stats {
                let key = fmt.string(from: day)
                records[key, default: DailyRecord(date: key)]
                    .metrics[id.rawValue] = value
            }
        }
        return records.values.sorted { $0.date < $1.date }
    }

    private func dailyAverages(for type: HKQuantityType, from start: Date, to end: Date,
                               calendar: Calendar) async throws -> [Date: Double] {
        try await withCheckedThrowingContinuation { cont in
            let query = HKStatisticsCollectionQuery(
                quantityType: type,
                quantitySamplePredicate: HKQuery.predicateForSamples(withStart: start, end: end),
                options: .discreteAverage,
                anchorDate: start,
                intervalComponents: DateComponents(day: 1))
            query.initialResultsHandler = { _, results, error in
                if let error { cont.resume(throwing: error); return }
                var out: [Date: Double] = [:]
                results?.enumerateStatistics(from: start, to: end) { stat, _ in
                    if let avg = stat.averageQuantity() {
                        out[stat.startDate] = avg.doubleValue(for: Self.unit(for: type))
                    }
                }
                cont.resume(returning: out)
            }
            store.execute(query)
        }
    }

    private static func unit(for type: HKQuantityType) -> HKUnit {
        switch type.identifier {
        case HKQuantityTypeIdentifier.heartRateVariabilitySDNN.rawValue:
            return .secondUnit(with: .milli)
        case HKQuantityTypeIdentifier.appleSleepingWristTemperature.rawValue:
            return .degreeCelsius()
        default:
            return HKUnit.count().unitDivided(by: .minute())
        }
    }

    func exportJSON(_ records: [DailyRecord]) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("sentinel_export.json")
        let enc = JSONEncoder()
        enc.outputFormatting = [.prettyPrinted, .sortedKeys]
        try enc.encode(records).write(to: url)
        return url
    }
}
