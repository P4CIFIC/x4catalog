import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count == 2 else {
    fputs("Usage: vision-ocr <image-path>\n", stderr)
    exit(64)
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: url), let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("Unable to decode image\n", stderr)
    exit(65)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])
let observations = request.results ?? []
let strings = observations.compactMap { $0.topCandidates(1).first?.string }
let areas = observations.map { $0.boundingBox.width * $0.boundingBox.height }
let heights = observations.map { $0.boundingBox.height * CGFloat(cgImage.height) }
let density = areas.reduce(0, +)
let minimum = heights.min() ?? 0
let payload: [String: Any] = [
    "text": strings.joined(separator: "\n"),
    "text_density": density,
    "minimum_text_height": minimum,
    "has_small_text": !strings.isEmpty && minimum < 18
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
