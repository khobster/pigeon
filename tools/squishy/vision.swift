import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
let img = NSImage(contentsOfFile: path)!
var rect = CGRect(origin: .zero, size: img.size)
let cg = img.cgImage(forProposedRect: &rect, context: nil, hints: nil)!
let W = CGFloat(cg.width), H = CGFloat(cg.height)
let handler = VNImageRequestHandler(cgImage: cg, options: [:])

let seg = VNGeneratePersonSegmentationRequest()
seg.qualityLevel = .accurate
seg.outputPixelFormat = kCVPixelFormatType_OneComponent8
let faces = VNDetectFaceLandmarksRequest()
try handler.perform([seg, faces])

if let mask = seg.results?.first?.pixelBuffer {
    let ci = CIImage(cvPixelBuffer: mask)
    let sx = W / ci.extent.width, sy = H / ci.extent.height
    let scaled = ci.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
    let ctx = CIContext()
    let out = ctx.createCGImage(scaled, from: CGRect(x: 0, y: 0, width: W, height: H))!
    let rep = NSBitmapImageRep(cgImage: out)
    try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "person.png"))
}
var json: [String: Any] = [:]
if let f = faces.results?.first {
    let bb = f.boundingBox
    json["box"] = [bb.minX * W, (1 - bb.maxY) * H, bb.width * W, bb.height * H]
    func pts(_ r: VNFaceLandmarkRegion2D?) -> [[CGFloat]] {
        guard let r = r else { return [] }
        return r.normalizedPoints.map { p in
            [ (bb.minX + p.x * bb.width) * W, (1 - (bb.minY + p.y * bb.height)) * H ] }
    }
    if let l = f.landmarks {
        json["leftEye"] = pts(l.leftEye); json["rightEye"] = pts(l.rightEye)
        json["leftBrow"] = pts(l.leftEyebrow); json["rightBrow"] = pts(l.rightEyebrow)
        json["nose"] = pts(l.nose); json["outerLips"] = pts(l.outerLips)
        json["contour"] = pts(l.faceContour); json["medianLine"] = pts(l.medianLine)
    }
}
let data = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted])
try data.write(to: URL(fileURLWithPath: "face.json"))
print("ok")
