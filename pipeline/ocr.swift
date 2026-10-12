// Recognise text on an image with Apple Vision; prints JSON lines:
// {"t": text, "x": left, "y": top, "w": width, "h": height} in pixels of the image.
// usage: swift ocr.swift IMAGE [IMAGE ...]  ->  one JSON array per image, written next to
// the output directory given by OCR_OUT (file name = image base name + ".json")
import Foundation
import Vision
import AppKit

let outDir = ProcessInfo.processInfo.environment["OCR_OUT"] ?? "."
for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    let out = URL(fileURLWithPath: outDir).appendingPathComponent(url.deletingPathExtension().lastPathComponent + ".json")
    if FileManager.default.fileExists(atPath: out.path) { continue }
    guard let img = NSImage(contentsOf: url), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("skip \(path)\n".data(using: .utf8)!); continue
    }
    let W = Double(cg.width), H = Double(cg.height)
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ru-RU", "en-US"]
    req.usesLanguageCorrection = true
    req.minimumTextHeight = 0.004
    do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch {
        FileHandle.standardError.write("fail \(path): \(error)\n".data(using: .utf8)!); continue
    }
    var rows: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        rows.append(["t": c.string, "x": Int(b.minX * W), "y": Int((1 - b.maxY) * H), "w": Int(b.width * W), "h": Int(b.height * H), "c": Double(c.confidence)])
    }
    let data = try! JSONSerialization.data(withJSONObject: ["w": Int(W), "h": Int(H), "lines": rows], options: [])
    try! data.write(to: out)
}
