# scSplit
### Genotype-free demultiplexing of pooled single-cell RNA-seq, using a hidden state model for identifying genetically distinct samples within a mixed population.  
#### It has been tested on up to 8 real mixed samples.

### To cite the package:
Xu, J., Falconer, C., Nguyen, Q. et al. Genotype-free demultiplexing of pooled single-cell RNA-seq. Genome Biol 20, 290 (2019). https://doi.org/10.1186/s13059-019-1852-7

### How to install:
  1) install python 3.6+
  2) make sure below python packages can be imported:
  
    numpy, pandas, pysam, PyVCF, scikit-learn, scipy, statistics
  3) "git clone https://<span></span>github.com/jon-xu/scSplit" or "pip  install scSplit" or simply download the scSplit file
  4) run with "\<PATH\>/scSplit \<command\> \<args\>" or "python \<PATH\>/scSplit \<command\> \<args\>" 

### Overall Pipeline:

![alt text](https://github.com/jon-xu/scSplit/blob/master/man/workflow.png)

### 1. Data quality control and filtering
   a) Filter processed BAM in a way that reads with any of following patterns be removed: read quality lower than 10,  being unmapped segment, being secondary alignment, not passing filters, being PCR or optical duplicate, or being supplementary alignment.
   
   e.g. samtools view -S -b -q 10 -F 3844 processed.bam > filtered.bam
   
   b) If necessary, remove duplicated reads based on UMI using tools like rmdup in UMI-tools.
   
   c) Sort and index the BAM file, using sort, index commands in samtools.
   
### 2. Calling for single-nucleotide variants
   a) Use freebayes v1.2 to call SNVs from the mixed sample BAM file after being processed in the first step, set the parameters for freebayes so that no insertion and deletions (indels), nor Multi-nucleotide polymorphysim (MNP) or complex events would be captured, set minimum allele count to 2 and set minimum base quality to 1.
   
   e.g. freebayes -f <reference.fa> -iXu -C 2 -q 1 filtered_rmdup_sorted.bam > snv.vcf
   
   This step could take very long (up to 30 hours if not using parallel processing).  In order to fasten the calling process, user can split the BAM by chromosome and call SNVs separately and merge the vcf files afterwards.
   
   Users can opt to use GATK or other SNV calling tools as well.  
   
   b) The output VCF file should be further filtered using bcftools so that only the SNVs with quality score larger than 30 would be kept.
   
   e.g. bcftools filter -i 'QUAL>30' snv.vcf -o filtered.vcf
   
### 3. Building allele count matrices
   a) Run "scSplit count" and get two .csv files ("ref_filtered.csv" and "alt_filtered.csv") as output.
   
   input parameters:
      
        -v, --vcf, VCF from mixed BAM
        -i, --bam, mixed sample BAM        
        -b, --bar, barcodes whitelist
        -t, --tag, tag for barcode (default: "CB")
        -c, --com, common SNVs    
        -r, --ref, output Ref count matrix        
        -a, --alt, output Alt count matrix
        -o, --out, output directory
        
        e.g. scSplit count -v filtered.vcf -i filtered_rmdup_sorted.bam -b barcodes.tsv -r ref_filtered.csv -a alt_filtered.csv -o .
   
   b) It is **strongly recommended** to use below SNV list to filter the matrices to improve prediction accuracy:

      Common SNPs (e.g. Human common SNPs from 1000 Genome project)
   
      hg19: http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/
   
      hg38: http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000_genomes_project/release/
        
      To process the genotype files of common SNPs, either download per-chromosome files and concatenate them using bcftools or download the whole genome file, take the first two columns of the vcf file and replace the tab with colon sign so that each line is one SNV, e.g., "1:10177". 
      
      Processed common SNVs for hg38 can be found here: https://melbourne.figshare.com/articles/dataset/Common_SNVS_hg38/17032163

   Please specify the common SNVs in scSplit count using -c/--com parameter, please make sure your common SNVs list does not have header row, and also please make sure the chromosome format in common SNV file is consistent with that in your data, e.g if your data use "chr1" rather than "1" to indicate the chromosome, you need to add "chr" at the beginning of each row of the common SNVs file before running scSplit.
   
   c) When building count matrices, the genotypes of each allele will be checked and only those heterozygous thus informative SNVs will be kept.  This is achieved by checking GL/GP/PL/GT fields in the VCF file, while only one in order will be used if existed.
   
   d) This step could be memory consuming, if the number of SNVs and/or cells are high. As a guideline, building matrices for 60,000 SNVs and 10,000 cells might need more than 30GB RAM to run, please allow enough RAM resource for running the script.
   
   e) Typical runtime for this step is about one hour, depending on the nature of the data and the resources being allocated.
   
   f) Typical number of filtered SNVs after this step is usually between 10,000 and 30,000.
   
   g) If this step fails, please check: 1) is your barcode tag in the BAM files "CB" - if not, you need to specify it using -t/--tag; 2) are you working on a mixed sample VCF rather than a simple merge of individual genotypes? 3) is the correct whitelist barcode file being used? The whitelist should be the trusted barcodes from your sequencing result, not the whole barcode library of the sequencing protocol.

### 4. Demultiplexing and generate ALT P/A matrix
   a) Use the two generated allele counts matrices files to demultiplex the cells into different samples.  Doublet sample will not have the same sample ID every time, which will be explicitly indicated in the log file
   
   b) Users can filter out doublets using dedicated tools like DoubletFinder before demultiplexing the sample (in this case please use -d 0 for demultiplexing pure singlets).

   c) Run "scSplit run" with input parameters:
      
        -r, --ref, input Ref count matrix        
        -a, --alt, input Alt count matrix        
        -n, --num, expected number of mixed samples (-n 0: autodetect mode)
        -o, --out, output directory
        -s, --sub, (optional) maximum number of subpopulations in autodetect mode, default: 10
        -e, --ems, (optional) number of EM repeats to avoid local maximum, default: 30
        -d, --dbl, (optional) correction for doublets, "-d 0" means you would expect no doublets.  There will be no refinement on the results if this optional parameter is not specified or specified percentage is less than doublet rates detected during the run
        -v, --vcf, (optional) known individual genotypes to limit distinguishing variants to available variants, so that users do not need to redo genotyping on selected variants, otherwise any variants could be selected as distinguishing variants.

        e.g. scSplit run -r ref_filtered.csv -a alt_filtered.csv -n 8 -o results
        
        # below command will tell the script to expect 20% doublets if the natually found doublets are less than that:
        e.g. scSplit run -r ref_filtered.csv -a alt_filtered.csv -n 8 -o results -d 0.2
        
        # (beta) -n 0 -s <sub>, let system decide the optimal sample number between 2 and <sub>
        e.g. scSplit run -r ref_filtered.csv -a alt_filtered.csv -n 0 -o results -s 12

   d) Below files will be generated:

      "scSplit_result.csv": barcodes assigned to each of the N+1 cluster (N singlets and 1 doublet cluster), doublet marked as DBL-<n> (n stands for the cluster number), e.g SNG-0 means the cluster 0 is a singlet cluster.
      "scSplit_dist_variants.txt": the distinguishing variants that can be used to genotype and assign sample to clusters
      "scSplit_dist_matrix.csv": the ALT allele Presence/Absence (P/A) matrix on distinguishing variants for all samples as a reference in assigning sample to clusters, NOT including the doublet cluster, whose sequence number would be different every run (please pay enough attention to this)
      "scSplit_PA_matrix.csv": the full ALT allele Presence/Absence (P/A) matrix for all samples, NOT including the doublet cluster, whose sequence number would be different every run (please pay enough attention to this)
      "scSplit_P_s_c.csv", the probability of each cell belonging to each sample
      "scSplit.log" log file containing information for current run, iterations, and final Maximum Likelihood and doublet sample
      
   e) This step is also memory consuming, and the RAM needed is highly dependent on the quantity of SNVs from last step and the number of cells. As a guideline, a matrix with 60,000 SNVs and 10,000 cells might need more than 50GB RAM to run, please allow enough RAM resource for running the script.
   
   f) Typical runtime for this step is about half an hour, with default parameters, depending on the nature of the data and the resources being allocated.
   
   g) scSplit will add one pseudo cluster to represent doublets.

### 5. (Optional) Generate sample genotypes based on the split result
   a) Run "scSplit genotype" with input parameters:
       
        -r, --ref, Ref count CSV as output        
        -a, --alt, Alt count CSV as output
        -p, --psc, generated P(S|C)
        -o, --out, output directory

        e.g. scSplit genotype -r ref_filtered.csv -a alt_filtered.csv -p scSplit_P_s_c.csv -o results
        
   b) VCF file ("scSplit.vcf") will be generated for the logarithm-transformed genotype likelihoods for all sample models.
   c) User can compare the genotypes on interesting SNPs with known sample genotypes on these SNPs and link the scSplit cluster to the samples. The largest value of GP or GL indicates the most probable genotype, e.g. GP 0.0, 0.295, 0.705 indicates a genotype of 1/1.

<br/>

