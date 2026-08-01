export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <div className="bg-white dark:bg-gray-900 p-8 md:p-12 rounded-xl shadow-sm border border-gray-200 dark:border-gray-800">
        <h1 className="text-4xl font-extrabold text-borr-navy dark:text-blue-300 mb-6">About BORR</h1>
        <p className="text-xl text-gray-600 dark:text-gray-400 mb-10 font-medium">Research for a Better Bangladesh.</p>

        <div className="prose prose-lg prose-blue max-w-none text-gray-700 dark:text-gray-300">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-8 mb-4">Our Mission</h2>
          <p className="mb-6 leading-relaxed">
            BORR (Bangladesh Open Research Repository) exists to make all research from Bangladesh — and about Bangladesh — discoverable, accessible, and free for anyone in the world to find. We aggregate all research metadata from global publishers into a single, searchable, open platform maintained by and for the people of Bangladesh.
          </p>

          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-8 mb-4">
            A Message from the Founders
          </h2>
          <div className="mb-8 rounded-lg border-l-4 border-borr-blue bg-blue-50 p-6 text-gray-700 dark:bg-blue-950/30 dark:text-gray-300">
            <p className="m-0 leading-relaxed">
              The Bangladesh Open Research Repository (BORR) is the thoughtful and carefully crafted vision of two brothers, Nehal Hasnain and Rehan Hasnain. We maintain this open research platform for Bangladeshi students, educators, researchers, and academics, with a mission to make Bangladeshi research more visible, accessible, and reachable to scholars around the world. We believe Bangladesh will lead frontier research in science, medicine, and technology, and we stand by our motto: &ldquo;Research for a Better Bangladesh.&rdquo;
            </p>
          </div>

          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-8 mb-4">The Problem We Solve</h2>
          <p className="mb-6 leading-relaxed">
            Bangladesh produces thousands of research papers annually across medicine, agriculture, engineering, climate science, and social sciences. Yet they are scattered across hundreds of publisher websites and institutional repositories. BORR acts as the missing &quot;front page&quot; for Bangladeshi science, bringing all this knowledge into one searchable index.
          </p>

          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-8 mb-4">How It Works</h2>
          <p className="mb-4 leading-relaxed">
            BORR is a metadata-only platform. <strong>We do not host or store any PDFs.</strong> Every paper links back to the original publisher.
          </p>
          <ul className="list-disc pl-6 mb-6 space-y-2">
            <li><strong>Automated Harvesting:</strong> Our system regularly queries global data and Crossref to find papers affiliated with Bangladeshi authors, institutions or concerning Bangladeshi topics.</li>
            <li><strong>Community Submissions:</strong> Researchers can submit their papers via DOI to be included in our index.</li>
          </ul>



          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-8 mb-4">Open Source</h2>
          <p className="mb-6 leading-relaxed">
            BORR is an open-source project released under the MIT License. You can view our code, contribute, or report issues on GitHub.
          </p>
          <a
            href="https://github.com/bdborr/borr"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center text-white bg-gray-900 dark:bg-gray-700 hover:bg-gray-800 dark:hover:bg-gray-600 px-6 py-3 rounded-md font-medium transition-colors"
          >
            View on GitHub
          </a>
        </div>
      </div>
    </div>
  );
}
