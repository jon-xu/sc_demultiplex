# sc_split
### Genotype-free demultiplexing of pooled single-cell RNAseq, using a hidden state model for identifying genetically distinct samples within a mixed population.  It has been used to demultiplex up to 8 samples on 10X platform.

### How to install:

### How to run the toolset:

##### 1. Data quality control and filtering
   *a) process BAM file from scRNA-Seq in a way that reads with any of following patterns be filtered out: quality is lower than 10,  is unmapped segment, is secondary alignment, not passing filters, is PCR or optical duplicate, or is supplementary alignment.*
   
   *b) from the processed BAM file, keep only the reads with white listed barcodes to reduce technical noises.*
   
   *c) Mark BAM file for duplication, and get it sorted and indexed.*
   
##### 2. Calling for single-nucleotide variants
   *a) use freebayes v1.2 to call SNVs from the mixed sample BAM file after being processed in the first step, set the parameters for freebayes so that no insertion and deletions (indels), nor Multi-nucleotide polymorphysim (MNP) or complex events would be captured, set minimum allele count to 2 and set minimum base quality to 1.*
   
   *b) The output VCF file will be futher filtered so that only the SNVs with quality score larger than 30 would be kept.*

##### 3. Building allele count matrices
   *run python script "sc_split_matrices.py" and get two .csv files ("ref_filtered.csv" and "alt_filtered.csv") as output.*

##### 4. Exectuion and verification of demultiplexing
   *use the two generated allele counts matrices files to demultiplex the cells into different samples.  Doublet sample will not have the same sample ID every time, which will be explicitly indicated in the log file*
   
   *run python script "sc_split_main.py"*
   
   *"barcodes_{n}.csv": N+1 indicating barcodes assigned to each of the N+1 samples (including doublet state)*
   *"model.found", a python pickle dump containing the final allele fraction model (model.model_MAF), and the probability of each cell belonging to each sample (model.P_s_c)*
   *"sc_split.log" log file containing information for current run, iterations, and final Maximum Likelihood and doublet sample*

##### 5. Output of Genotype likelihoods for models
   *run python script "sc_split_vcf.py"*
   
   *a VCF file ("sc_split.vcf") will be generated for the logarithm-transformed genotype likelihoods for all sample models.*
