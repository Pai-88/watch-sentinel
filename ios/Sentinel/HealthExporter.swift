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

    func requestAuthorization() async throws {
        let read = Set(types.compactMap { HKQuantityType.quantityType(forIdentifier: $0) })
        try await store.requestAuthorization(toShare: [], read: read)
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
